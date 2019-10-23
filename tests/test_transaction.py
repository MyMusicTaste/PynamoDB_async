import pytest
from asynctest.mock import patch
from pynamodb.attributes import NumberAttribute, UnicodeAttribute, VersionAttribute

from inpynamodb.connection import AsyncConnection
from inpynamodb.models import Model
from inpynamodb.transactions import Transaction, TransactGet, TransactWrite
from tests.test_base_connection import PATCH_METHOD


class MockModel(Model):
    class Meta:
        table_name = 'mock'

    mock_hash = NumberAttribute(hash_key=True)
    mock_range = NumberAttribute(range_key=True)
    mock_toot = UnicodeAttribute(null=True)
    mock_version = VersionAttribute()


MOCK_TABLE_DESCRIPTOR = {
    "Table": {
        "TableName": "Mock",
        "KeySchema": [
            {
                "AttributeName": "MockHash",
                "KeyType": "HASH"
            },
            {
                "AttributeName": "MockRange",
                "KeyType": "RANGE"
            }
        ],
        "AttributeDefinitions": [
            {
                "AttributeName": "MockHash",
                "AttributeType": "N"
            },
            {
                "AttributeName": "MockRange",
                "AttributeType": "N"
            }
        ]
    }
}


class TestTransaction:
    @pytest.mark.asyncio
    async def test_commit__not_implemented(self):
        t = Transaction(connection=AsyncConnection())
        with pytest.raises(NotImplementedError):
            await t._commit()


class TestTransactGet:
    @pytest.mark.asyncio
    async def test_commit(self):
        connection = AsyncConnection()

        with patch('inpynamodb.connection.AsyncConnection.transact_get_items') as mock_connection_transact_get:
            with patch(PATCH_METHOD) as req:
                req.return_value = MOCK_TABLE_DESCRIPTOR
                async with TransactGet(connection=connection) as t:
                    await t.get(MockModel, 1, 2)

            mock_connection_transact_get.assert_called_once_with(
                get_items=[{'Key': {'MockHash': {'N': '1'}, 'MockRange': {'N': '2'}}, 'TableName': 'mock'}],
                return_consumed_capacity=None
            )


class TestTransactWrite:
    @pytest.mark.asyncio
    async def test_condition_check__no_condition(self):
        with pytest.raises(TypeError):
            async with TransactWrite(connection=AsyncConnection()) as transaction:
                await transaction.condition_check(MockModel, hash_key=1, condition=None)

    @pytest.mark.asyncio
    async def test_commit(self):
        connection = AsyncConnection()
        with patch('inpynamodb.connection.AsyncConnection.transact_write_items') as mock_connection_transact_write:
            with patch(PATCH_METHOD) as req:
                req.return_value = MOCK_TABLE_DESCRIPTOR
                async with TransactWrite(connection=connection) as t:
                    await t.condition_check(MockModel, 1, 3, condition=(MockModel.mock_hash.does_not_exist()))
                    await t.delete(MockModel(2, 4))
                    await t.save(MockModel(3, 5))
                    await t.update(MockModel(4, 6), actions=[MockModel.mock_toot.set('hello')], return_values='ALL_OLD')

            expected_condition_checks = [{
                'ConditionExpression': 'attribute_not_exists (#0)',
                'ExpressionAttributeNames': {'#0': 'mock_hash'},
                'Key': {'MockHash': {'N': '1'}, 'MockRange': {'N': '3'}},
                'TableName': 'mock'}
            ]
            expected_deletes = [{
                'ConditionExpression': 'attribute_not_exists (#0)',
                'ExpressionAttributeNames': {'#0': 'mock_version'},
                'Key': {'MockHash': {'N': '2'}, 'MockRange': {'N': '4'}},
                'TableName': 'mock'
            }]
            expected_puts = [{
                'ConditionExpression': 'attribute_not_exists (#0)',
                'ExpressionAttributeNames': {'#0': 'mock_version'},
                'Item': {'MockHash': {'N': '3'}, 'MockRange': {'N': '5'}, 'mock_version': {'N': '1'}},
                'TableName': 'mock'
            }]
            expected_updates = [{
                'ConditionExpression': 'attribute_not_exists (#0)',
                'TableName': 'mock',
                'Key': {'MockHash': {'N': '4'}, 'MockRange': {'N': '6'}},
                'ReturnValuesOnConditionCheckFailure': 'ALL_OLD',
                'UpdateExpression': 'SET #1 = :0, #0 = :1',
                'ExpressionAttributeNames': {'#0': 'mock_version', '#1': 'mock_toot'},
                'ExpressionAttributeValues': {':0': {'S': 'hello'}, ':1': {'N': '1'}}
            }]

            mock_connection_transact_write.assert_called_once_with(
                condition_check_items=expected_condition_checks,
                delete_items=expected_deletes,
                put_items=expected_puts,
                update_items=expected_updates,
                client_request_token=None,
                return_consumed_capacity=None,
                return_item_collection_metrics=None
            )
