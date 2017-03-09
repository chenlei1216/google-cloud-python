# Copyright 2014 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

import mock


def _make_credentials():
    import google.auth.credentials

    return mock.Mock(spec=google.auth.credentials.Credentials)


def _make_entity_pb(project, kind, integer_id, name=None, str_val=None):
    from google.cloud.proto.datastore.v1 import entity_pb2
    from google.cloud.datastore.helpers import _new_value_pb

    entity_pb = entity_pb2.Entity()
    entity_pb.key.partition_id.project_id = project
    path_element = entity_pb.key.path.add()
    path_element.kind = kind
    path_element.id = integer_id
    if name is not None and str_val is not None:
        value_pb = _new_value_pb(entity_pb, name)
        value_pb.string_value = str_val

    return entity_pb


class Test__get_gcd_project(unittest.TestCase):

    def _call_fut(self):
        from google.cloud.datastore.client import _get_gcd_project

        return _get_gcd_project()

    def test_no_value(self):
        environ = {}
        with mock.patch('os.getenv', new=environ.get):
            project = self._call_fut()
            self.assertIsNone(project)

    def test_value_set(self):
        from google.cloud.datastore.client import GCD_DATASET

        MOCK_PROJECT = object()
        environ = {GCD_DATASET: MOCK_PROJECT}
        with mock.patch('os.getenv', new=environ.get):
            project = self._call_fut()
            self.assertEqual(project, MOCK_PROJECT)


class Test__determine_default_project(unittest.TestCase):

    def _call_fut(self, project=None):
        from google.cloud.datastore.client import (
            _determine_default_project)

        return _determine_default_project(project=project)

    def _determine_default_helper(self, gcd=None, fallback=None,
                                  project_called=None):
        _callers = []

        def gcd_mock():
            _callers.append('gcd_mock')
            return gcd

        def fallback_mock(project=None):
            _callers.append(('fallback_mock', project))
            return fallback

        patch = mock.patch.multiple(
            'google.cloud.datastore.client',
            _get_gcd_project=gcd_mock,
            _base_default_project=fallback_mock)
        with patch:
            returned_project = self._call_fut(project_called)

        return returned_project, _callers

    def test_no_value(self):
        project, callers = self._determine_default_helper()
        self.assertIsNone(project)
        self.assertEqual(callers, ['gcd_mock', ('fallback_mock', None)])

    def test_explicit(self):
        PROJECT = object()
        project, callers = self._determine_default_helper(
            project_called=PROJECT)
        self.assertEqual(project, PROJECT)
        self.assertEqual(callers, [])

    def test_gcd(self):
        PROJECT = object()
        project, callers = self._determine_default_helper(gcd=PROJECT)
        self.assertEqual(project, PROJECT)
        self.assertEqual(callers, ['gcd_mock'])

    def test_fallback(self):
        PROJECT = object()
        project, callers = self._determine_default_helper(fallback=PROJECT)
        self.assertEqual(project, PROJECT)
        self.assertEqual(callers, ['gcd_mock', ('fallback_mock', None)])


class TestClient(unittest.TestCase):

    PROJECT = 'PROJECT'

    def setUp(self):
        from google.cloud.datastore import client as MUT

        self.original_cnxn_class = MUT.Connection
        MUT.Connection = _MockConnection

    def tearDown(self):
        from google.cloud.datastore import client as MUT

        MUT.Connection = self.original_cnxn_class

    @staticmethod
    def _get_target_class():
        from google.cloud.datastore.client import Client

        return Client

    def _make_one(self, project=PROJECT, namespace=None,
                  credentials=None, http=None, use_gax=None):
        return self._get_target_class()(project=project,
                                        namespace=namespace,
                                        credentials=credentials,
                                        http=http,
                                        use_gax=use_gax)

    def test_constructor_w_project_no_environ(self):
        # Some environments (e.g. AppVeyor CI) run in GCE, so
        # this test would fail artificially.
        patch = mock.patch(
            'google.cloud.datastore.client._base_default_project',
            return_value=None)
        with patch:
            self.assertRaises(EnvironmentError, self._make_one, None)

    def test_constructor_w_implicit_inputs(self):
        from google.cloud.datastore.client import _DATASTORE_BASE_URL

        other = 'other'
        creds = _make_credentials()
        default_called = []

        def fallback_mock(project):
            default_called.append(project)
            return project or other

        klass = self._get_target_class()
        patch1 = mock.patch(
            'google.cloud.datastore.client._determine_default_project',
            new=fallback_mock)
        patch2 = mock.patch(
            'google.cloud.client.get_credentials',
            return_value=creds)

        with patch1:
            with patch2:
                client = klass()

        self.assertEqual(client.project, other)
        self.assertIsNone(client.namespace)
        self.assertIsInstance(client._connection, _MockConnection)
        self.assertIs(client._credentials, creds)
        self.assertIsNone(client._http_internal)
        self.assertEqual(client._base_url, _DATASTORE_BASE_URL)

        self.assertIsNone(client.current_batch)
        self.assertIsNone(client.current_transaction)
        self.assertEqual(default_called, [None])

    def test_constructor_w_explicit_inputs(self):
        from google.cloud.datastore.client import _DATASTORE_BASE_URL

        other = 'other'
        namespace = 'namespace'
        creds = _make_credentials()
        http = object()
        client = self._make_one(project=other,
                                namespace=namespace,
                                credentials=creds,
                                http=http)
        self.assertEqual(client.project, other)
        self.assertEqual(client.namespace, namespace)
        self.assertIsInstance(client._connection, _MockConnection)
        self.assertIs(client._credentials, creds)
        self.assertIs(client._http_internal, http)
        self.assertIsNone(client.current_batch)
        self.assertEqual(list(client._batch_stack), [])
        self.assertEqual(client._base_url, _DATASTORE_BASE_URL)

    def test_constructor_use_gax_default(self):
        import google.cloud.datastore.client as MUT

        project = 'PROJECT'
        creds = _make_credentials()
        http = object()

        with mock.patch.object(MUT, '_USE_GAX', new=True):
            client1 = self._make_one(
                project=project, credentials=creds, http=http)
            self.assertTrue(client1._use_gax)
            # Explicitly over-ride the environment.
            client2 = self._make_one(
                project=project, credentials=creds, http=http,
                use_gax=False)
            self.assertFalse(client2._use_gax)

        with mock.patch.object(MUT, '_USE_GAX', new=False):
            client3 = self._make_one(
                project=project, credentials=creds, http=http)
            self.assertFalse(client3._use_gax)
            # Explicitly over-ride the environment.
            client4 = self._make_one(
                project=project, credentials=creds, http=http,
                use_gax=True)
            self.assertTrue(client4._use_gax)

    def test_constructor_gcd_host(self):
        from google.cloud.environment_vars import GCD_HOST

        host = 'localhost:1234'
        fake_environ = {GCD_HOST: host}
        project = 'PROJECT'
        creds = _make_credentials()
        http = object()

        with mock.patch('os.environ', new=fake_environ):
            client = self._make_one(
                project=project, credentials=creds, http=http)
            self.assertEqual(client._base_url, 'http://' + host)

    def test__datastore_api_property_gax(self):
        client = self._make_one(
            project='prahj-ekt', credentials=_make_credentials(),
            http=object(), use_gax=True)

        self.assertIsNone(client._datastore_api_internal)
        patch = mock.patch(
            'google.cloud.datastore.client.make_datastore_api',
            return_value=mock.sentinel.ds_api)
        with patch as make_api:
            ds_api = client._datastore_api
            self.assertIs(ds_api, mock.sentinel.ds_api)
            make_api.assert_called_once_with(client)
            self.assertIs(
                client._datastore_api_internal, mock.sentinel.ds_api)
            # Make sure the cached value is used.
            self.assertEqual(make_api.call_count, 1)
            self.assertIs(
                client._datastore_api, mock.sentinel.ds_api)
            self.assertEqual(make_api.call_count, 1)

    def test__datastore_api_property_http(self):
        from google.cloud.datastore._http import HTTPDatastoreAPI

        client = self._make_one(
            project='prahj-ekt', credentials=_make_credentials(),
            http=object(), use_gax=False)

        self.assertIsNone(client._datastore_api_internal)
        ds_api = client._datastore_api
        self.assertIsInstance(ds_api, HTTPDatastoreAPI)
        self.assertIs(ds_api.client, client)
        # Make sure the cached value is used.
        self.assertIs(client._datastore_api_internal, ds_api)
        self.assertIs(client._datastore_api, ds_api)

    def test__push_batch_and__pop_batch(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        batch = client.batch()
        xact = client.transaction()
        client._push_batch(batch)
        self.assertEqual(list(client._batch_stack), [batch])
        self.assertIs(client.current_batch, batch)
        self.assertIsNone(client.current_transaction)
        client._push_batch(xact)
        self.assertIs(client.current_batch, xact)
        self.assertIs(client.current_transaction, xact)
        # list(_LocalStack) returns in reverse order.
        self.assertEqual(list(client._batch_stack), [xact, batch])
        self.assertIs(client._pop_batch(), xact)
        self.assertEqual(list(client._batch_stack), [batch])
        self.assertIs(client._pop_batch(), batch)
        self.assertEqual(list(client._batch_stack), [])

    def test_get_miss(self):
        _called_with = []

        def _get_multi(*args, **kw):
            _called_with.append((args, kw))
            return []

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client.get_multi = _get_multi

        key = object()

        self.assertIsNone(client.get(key))

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['keys'], [key])
        self.assertIsNone(_called_with[0][1]['missing'])
        self.assertIsNone(_called_with[0][1]['deferred'])
        self.assertIsNone(_called_with[0][1]['transaction'])

    def test_get_hit(self):
        TXN_ID = '123'
        _called_with = []
        _entity = object()

        def _get_multi(*args, **kw):
            _called_with.append((args, kw))
            return [_entity]

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client.get_multi = _get_multi

        key, missing, deferred = object(), [], []

        self.assertIs(client.get(key, missing, deferred, TXN_ID), _entity)

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['keys'], [key])
        self.assertIs(_called_with[0][1]['missing'], missing)
        self.assertIs(_called_with[0][1]['deferred'], deferred)
        self.assertEqual(_called_with[0][1]['transaction'], TXN_ID)

    def test_get_multi_no_keys(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        results = client.get_multi([])
        self.assertEqual(results, [])

    def test_get_multi_miss(self):
        from google.cloud.datastore.key import Key

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client._connection._add_lookup_result()
        key = Key('Kind', 1234, project=self.PROJECT)
        results = client.get_multi([key])
        self.assertEqual(results, [])

    def test_get_multi_miss_w_missing(self):
        from google.cloud.proto.datastore.v1 import entity_pb2
        from google.cloud.datastore.key import Key

        KIND = 'Kind'
        ID = 1234

        # Make a missing entity pb to be returned from mock backend.
        missed = entity_pb2.Entity()
        missed.key.partition_id.project_id = self.PROJECT
        path_element = missed.key.path.add()
        path_element.kind = KIND
        path_element.id = ID

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        # Set missing entity on mock connection.
        client._connection._add_lookup_result(missing=[missed])

        key = Key(KIND, ID, project=self.PROJECT)
        missing = []
        entities = client.get_multi([key], missing=missing)
        self.assertEqual(entities, [])
        self.assertEqual([missed.key.to_protobuf() for missed in missing],
                         [key.to_protobuf()])

    def test_get_multi_w_missing_non_empty(self):
        from google.cloud.datastore.key import Key

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        key = Key('Kind', 1234, project=self.PROJECT)

        missing = ['this', 'list', 'is', 'not', 'empty']
        self.assertRaises(ValueError, client.get_multi,
                          [key], missing=missing)

    def test_get_multi_w_deferred_non_empty(self):
        from google.cloud.datastore.key import Key

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        key = Key('Kind', 1234, project=self.PROJECT)

        deferred = ['this', 'list', 'is', 'not', 'empty']
        self.assertRaises(ValueError, client.get_multi,
                          [key], deferred=deferred)

    def test_get_multi_miss_w_deferred(self):
        from google.cloud.datastore.key import Key

        key = Key('Kind', 1234, project=self.PROJECT)

        # Set deferred entity on mock connection.
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client._connection._add_lookup_result(deferred=[key.to_protobuf()])

        deferred = []
        entities = client.get_multi([key], deferred=deferred)
        self.assertEqual(entities, [])
        self.assertEqual([def_key.to_protobuf() for def_key in deferred],
                         [key.to_protobuf()])

    def test_get_multi_w_deferred_from_backend_but_not_passed(self):
        from google.cloud.proto.datastore.v1 import entity_pb2
        from google.cloud.datastore.entity import Entity
        from google.cloud.datastore.key import Key

        key1 = Key('Kind', project=self.PROJECT)
        key1_pb = key1.to_protobuf()
        key2 = Key('Kind', 2345, project=self.PROJECT)
        key2_pb = key2.to_protobuf()

        entity1_pb = entity_pb2.Entity()
        entity1_pb.key.CopyFrom(key1_pb)
        entity2_pb = entity_pb2.Entity()
        entity2_pb.key.CopyFrom(key2_pb)

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        # mock up two separate requests
        client._connection._add_lookup_result([entity1_pb], deferred=[key2_pb])
        client._connection._add_lookup_result([entity2_pb])

        missing = []
        found = client.get_multi([key1, key2], missing=missing)
        self.assertEqual(len(found), 2)
        self.assertEqual(len(missing), 0)

        # Check the actual contents on the response.
        self.assertIsInstance(found[0], Entity)
        self.assertEqual(found[0].key.path, key1.path)
        self.assertEqual(found[0].key.project, key1.project)

        self.assertIsInstance(found[1], Entity)
        self.assertEqual(found[1].key.path, key2.path)
        self.assertEqual(found[1].key.project, key2.project)

        cw = client._connection._lookup_cw
        self.assertEqual(len(cw), 2)

        ds_id, k_pbs, eventual, tid = cw[0]
        self.assertEqual(ds_id, self.PROJECT)
        self.assertEqual(len(k_pbs), 2)
        self.assertEqual(key1_pb, k_pbs[0])
        self.assertEqual(key2_pb, k_pbs[1])
        self.assertFalse(eventual)
        self.assertIsNone(tid)

        ds_id, k_pbs, eventual, tid = cw[1]
        self.assertEqual(ds_id, self.PROJECT)
        self.assertEqual(len(k_pbs), 1)
        self.assertEqual(key2_pb, k_pbs[0])
        self.assertFalse(eventual)
        self.assertIsNone(tid)

    def test_get_multi_hit(self):
        from google.cloud.datastore.key import Key

        KIND = 'Kind'
        ID = 1234
        PATH = [{'kind': KIND, 'id': ID}]

        # Make a found entity pb to be returned from mock backend.
        entity_pb = _make_entity_pb(self.PROJECT, KIND, ID, 'foo', 'Foo')

        # Make a connection to return the entity pb.
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client._connection._add_lookup_result([entity_pb])

        key = Key(KIND, ID, project=self.PROJECT)
        result, = client.get_multi([key])
        new_key = result.key

        # Check the returned value is as expected.
        self.assertIsNot(new_key, key)
        self.assertEqual(new_key.project, self.PROJECT)
        self.assertEqual(new_key.path, PATH)
        self.assertEqual(list(result), ['foo'])
        self.assertEqual(result['foo'], 'Foo')

    def test_get_multi_hit_w_transaction(self):
        from google.cloud.datastore.key import Key

        TXN_ID = '123'
        KIND = 'Kind'
        ID = 1234
        PATH = [{'kind': KIND, 'id': ID}]

        # Make a found entity pb to be returned from mock backend.
        entity_pb = _make_entity_pb(self.PROJECT, KIND, ID, 'foo', 'Foo')

        # Make a connection to return the entity pb.
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client._connection._add_lookup_result([entity_pb])

        key = Key(KIND, ID, project=self.PROJECT)
        txn = client.transaction()
        txn._id = TXN_ID
        result, = client.get_multi([key], transaction=txn)
        new_key = result.key

        # Check the returned value is as expected.
        self.assertIsNot(new_key, key)
        self.assertEqual(new_key.project, self.PROJECT)
        self.assertEqual(new_key.path, PATH)
        self.assertEqual(list(result), ['foo'])
        self.assertEqual(result['foo'], 'Foo')

        cw = client._connection._lookup_cw
        self.assertEqual(len(cw), 1)
        _, _, _, transaction_id = cw[0]
        self.assertEqual(transaction_id, TXN_ID)

    def test_get_multi_hit_multiple_keys_same_project(self):
        from google.cloud.datastore.key import Key

        KIND = 'Kind'
        ID1 = 1234
        ID2 = 2345

        # Make a found entity pb to be returned from mock backend.
        entity_pb1 = _make_entity_pb(self.PROJECT, KIND, ID1)
        entity_pb2 = _make_entity_pb(self.PROJECT, KIND, ID2)

        # Make a connection to return the entity pbs.
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client._connection._add_lookup_result([entity_pb1, entity_pb2])

        key1 = Key(KIND, ID1, project=self.PROJECT)
        key2 = Key(KIND, ID2, project=self.PROJECT)
        retrieved1, retrieved2 = client.get_multi([key1, key2])

        # Check values match.
        self.assertEqual(retrieved1.key.path, key1.path)
        self.assertEqual(dict(retrieved1), {})
        self.assertEqual(retrieved2.key.path, key2.path)
        self.assertEqual(dict(retrieved2), {})

    def test_get_multi_hit_multiple_keys_different_project(self):
        from google.cloud.datastore.key import Key

        PROJECT1 = 'PROJECT'
        PROJECT2 = 'PROJECT-ALT'

        # Make sure our IDs are actually different.
        self.assertNotEqual(PROJECT1, PROJECT2)

        key1 = Key('KIND', 1234, project=PROJECT1)
        key2 = Key('KIND', 1234, project=PROJECT2)

        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        with self.assertRaises(ValueError):
            client.get_multi([key1, key2])

    def test_get_multi_max_loops(self):
        from google.cloud.datastore.key import Key

        KIND = 'Kind'
        ID = 1234

        # Make a found entity pb to be returned from mock backend.
        entity_pb = _make_entity_pb(self.PROJECT, KIND, ID, 'foo', 'Foo')

        # Make a connection to return the entity pb.
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client._connection._add_lookup_result([entity_pb])

        key = Key(KIND, ID, project=self.PROJECT)
        deferred = []
        missing = []

        patch = mock.patch(
            'google.cloud.datastore.client._MAX_LOOPS', new=-1)
        with patch:
            result = client.get_multi([key], missing=missing,
                                      deferred=deferred)

        # Make sure we have no results, even though the connection has been
        # set up as in `test_hit` to return a single result.
        self.assertEqual(result, [])
        self.assertEqual(missing, [])
        self.assertEqual(deferred, [])

    def test_put(self):
        _called_with = []

        def _put_multi(*args, **kw):
            _called_with.append((args, kw))

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client.put_multi = _put_multi
        entity = object()

        client.put(entity)

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['entities'], [entity])

    def test_put_multi_no_entities(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        self.assertIsNone(client.put_multi([]))

    def test_put_multi_w_single_empty_entity(self):
        # https://github.com/GoogleCloudPlatform/google-cloud-python/issues/649
        from google.cloud.datastore.entity import Entity

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        self.assertRaises(ValueError, client.put_multi, Entity())

    def test_put_multi_no_batch_w_partial_key(self):
        from google.cloud.datastore.helpers import _property_tuples

        entity = _Entity(foo=u'bar')
        key = entity.key = _Key(self.PROJECT)
        key._id = None

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        key_pb = _make_key(234)
        client._connection._commit.append([key_pb])

        result = client.put_multi([entity])
        self.assertIsNone(result)

        self.assertEqual(len(client._connection._commit_cw), 1)
        (project,
         commit_req, transaction_id) = client._connection._commit_cw[0]
        self.assertEqual(project, self.PROJECT)

        mutated_entity = _mutated_pb(self, commit_req.mutations, 'insert')
        self.assertEqual(mutated_entity.key, key.to_protobuf())

        prop_list = list(_property_tuples(mutated_entity))
        self.assertTrue(len(prop_list), 1)
        name, value_pb = prop_list[0]
        self.assertEqual(name, 'foo')
        self.assertEqual(value_pb.string_value, u'bar')

        self.assertIsNone(transaction_id)

    def test_put_multi_existing_batch_w_completed_key(self):
        from google.cloud.datastore.helpers import _property_tuples

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        entity = _Entity(foo=u'bar')
        key = entity.key = _Key(self.PROJECT)

        with _NoCommitBatch(client) as CURR_BATCH:
            result = client.put_multi([entity])

        self.assertIsNone(result)
        mutated_entity = _mutated_pb(self, CURR_BATCH.mutations, 'upsert')
        self.assertEqual(mutated_entity.key, key.to_protobuf())

        prop_list = list(_property_tuples(mutated_entity))
        self.assertTrue(len(prop_list), 1)
        name, value_pb = prop_list[0]
        self.assertEqual(name, 'foo')
        self.assertEqual(value_pb.string_value, u'bar')

    def test_delete(self):
        _called_with = []

        def _delete_multi(*args, **kw):
            _called_with.append((args, kw))

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client.delete_multi = _delete_multi
        key = object()

        client.delete(key)

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['keys'], [key])

    def test_delete_multi_no_keys(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        result = client.delete_multi([])
        self.assertIsNone(result)
        self.assertEqual(len(client._connection._commit_cw), 0)

    def test_delete_multi_no_batch(self):
        key = _Key(self.PROJECT)

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        client._connection._commit.append([])

        result = client.delete_multi([key])
        self.assertIsNone(result)
        self.assertEqual(len(client._connection._commit_cw), 1)
        (project,
         commit_req, transaction_id) = client._connection._commit_cw[0]
        self.assertEqual(project, self.PROJECT)

        mutated_key = _mutated_pb(self, commit_req.mutations, 'delete')
        self.assertEqual(mutated_key, key.to_protobuf())
        self.assertIsNone(transaction_id)

    def test_delete_multi_w_existing_batch(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        key = _Key(self.PROJECT)

        with _NoCommitBatch(client) as CURR_BATCH:
            result = client.delete_multi([key])

        self.assertIsNone(result)
        mutated_key = _mutated_pb(self, CURR_BATCH.mutations, 'delete')
        self.assertEqual(mutated_key, key._key)
        self.assertEqual(len(client._connection._commit_cw), 0)

    def test_delete_multi_w_existing_transaction(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        key = _Key(self.PROJECT)

        with _NoCommitTransaction(client) as CURR_XACT:
            result = client.delete_multi([key])

        self.assertIsNone(result)
        mutated_key = _mutated_pb(self, CURR_XACT.mutations, 'delete')
        self.assertEqual(mutated_key, key._key)
        self.assertEqual(len(client._connection._commit_cw), 0)

    def test_allocate_ids_w_partial_key(self):
        num_ids = 2

        incomplete_key = _Key(self.PROJECT)
        incomplete_key._id = None

        creds = _make_credentials()
        client = self._make_one(credentials=creds, use_gax=False)
        allocated = mock.Mock(
            keys=[_KeyPB(i) for i in range(num_ids)], spec=['keys'])
        alloc_ids = mock.Mock(return_value=allocated, spec=[])
        ds_api = mock.Mock(allocate_ids=alloc_ids, spec=['allocate_ids'])
        client._datastore_api_internal = ds_api

        result = client.allocate_ids(incomplete_key, num_ids)

        # Check the IDs returned.
        self.assertEqual([key._id for key in result], list(range(num_ids)))

    def test_allocate_ids_with_completed_key(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        COMPLETE_KEY = _Key(self.PROJECT)
        self.assertRaises(ValueError, client.allocate_ids, COMPLETE_KEY, 2)

    def test_key_w_project(self):
        KIND = 'KIND'
        ID = 1234

        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        self.assertRaises(TypeError,
                          client.key, KIND, ID, project=self.PROJECT)

    def test_key_wo_project(self):
        kind = 'KIND'
        id_ = 1234

        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Key', spec=['__call__'])
        with patch as mock_klass:
            key = client.key(kind, id_)
            self.assertIs(key, mock_klass.return_value)
            mock_klass.assert_called_once_with(
                kind, id_, project=self.PROJECT, namespace=None)

    def test_key_w_namespace(self):
        kind = 'KIND'
        id_ = 1234
        namespace = object()

        creds = _make_credentials()
        client = self._make_one(namespace=namespace, credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Key', spec=['__call__'])
        with patch as mock_klass:
            key = client.key(kind, id_)
            self.assertIs(key, mock_klass.return_value)
            mock_klass.assert_called_once_with(
                kind, id_, project=self.PROJECT, namespace=namespace)

    def test_key_w_namespace_collision(self):
        kind = 'KIND'
        id_ = 1234
        namespace1 = object()
        namespace2 = object()

        creds = _make_credentials()
        client = self._make_one(namespace=namespace1, credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Key', spec=['__call__'])
        with patch as mock_klass:
            key = client.key(kind, id_, namespace=namespace2)
            self.assertIs(key, mock_klass.return_value)
            mock_klass.assert_called_once_with(
                kind, id_, project=self.PROJECT, namespace=namespace2)

    def test_batch(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Batch', spec=['__call__'])
        with patch as mock_klass:
            batch = client.batch()
            self.assertIs(batch, mock_klass.return_value)
            mock_klass.assert_called_once_with(client)

    def test_transaction_defaults(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Transaction', spec=['__call__'])
        with patch as mock_klass:
            xact = client.transaction()
            self.assertIs(xact, mock_klass.return_value)
            mock_klass.assert_called_once_with(client)

    def test_query_w_client(self):
        KIND = 'KIND'

        creds = _make_credentials()
        client = self._make_one(credentials=creds)
        other = self._make_one(credentials=_make_credentials())

        self.assertRaises(TypeError, client.query, kind=KIND, client=other)

    def test_query_w_project(self):
        KIND = 'KIND'

        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        self.assertRaises(TypeError,
                          client.query, kind=KIND, project=self.PROJECT)

    def test_query_w_defaults(self):
        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Query', spec=['__call__'])
        with patch as mock_klass:
            query = client.query()
            self.assertIs(query, mock_klass.return_value)
            mock_klass.assert_called_once_with(
                client, project=self.PROJECT, namespace=None)

    def test_query_explicit(self):
        kind = 'KIND'
        namespace = 'NAMESPACE'
        ancestor = object()
        filters = [('PROPERTY', '==', 'VALUE')]
        projection = ['__key__']
        order = ['PROPERTY']
        distinct_on = ['DISTINCT_ON']

        creds = _make_credentials()
        client = self._make_one(credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Query', spec=['__call__'])
        with patch as mock_klass:
            query = client.query(
                kind=kind,
                namespace=namespace,
                ancestor=ancestor,
                filters=filters,
                projection=projection,
                order=order,
                distinct_on=distinct_on,
            )
            self.assertIs(query, mock_klass.return_value)
            mock_klass.assert_called_once_with(
                client,
                project=self.PROJECT,
                kind=kind,
                namespace=namespace,
                ancestor=ancestor,
                filters=filters,
                projection=projection,
                order=order,
                distinct_on=distinct_on,
            )

    def test_query_w_namespace(self):
        kind = 'KIND'
        namespace = object()

        creds = _make_credentials()
        client = self._make_one(namespace=namespace, credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Query', spec=['__call__'])
        with patch as mock_klass:
            query = client.query(kind=kind)
            self.assertIs(query, mock_klass.return_value)
            mock_klass.assert_called_once_with(
                client, project=self.PROJECT, namespace=namespace, kind=kind)

    def test_query_w_namespace_collision(self):
        kind = 'KIND'
        namespace1 = object()
        namespace2 = object()

        creds = _make_credentials()
        client = self._make_one(namespace=namespace1, credentials=creds)

        patch = mock.patch(
            'google.cloud.datastore.client.Query', spec=['__call__'])
        with patch as mock_klass:
            query = client.query(kind=kind, namespace=namespace2)
            self.assertIs(query, mock_klass.return_value)
            mock_klass.assert_called_once_with(
                client, project=self.PROJECT, namespace=namespace2, kind=kind)


class _MockConnection(object):

    def __init__(self, credentials=None, http=None):
        self.credentials = credentials
        self.http = http
        self._lookup_cw = []
        self._lookup = []
        self._commit_cw = []
        self._commit = []

    def _add_lookup_result(self, results=(), missing=(), deferred=()):
        self._lookup.append((list(results), list(missing), list(deferred)))

    def lookup(self, project, key_pbs, eventual=False, transaction_id=None):
        self._lookup_cw.append((project, key_pbs, eventual, transaction_id))
        triple, self._lookup = self._lookup[0], self._lookup[1:]
        results, missing, deferred = triple

        entity_results_found = [
            mock.Mock(entity=result, spec=['entity']) for result in results]
        entity_results_missing = [
            mock.Mock(entity=missing_entity, spec=['entity'])
            for missing_entity in missing]
        return mock.Mock(
            found=entity_results_found,
            missing=entity_results_missing,
            deferred=deferred,
            spec=['found', 'missing', 'deferred'])

    def commit(self, project, commit_request, transaction_id):
        from google.cloud.proto.datastore.v1 import datastore_pb2

        self._commit_cw.append((project, commit_request, transaction_id))
        keys, self._commit = self._commit[0], self._commit[1:]
        mutation_results = [
            datastore_pb2.MutationResult(key=key) for key in keys]
        return datastore_pb2.CommitResponse(mutation_results=mutation_results)


class _NoCommitBatch(object):

    def __init__(self, client):
        from google.cloud.datastore.batch import Batch

        self._client = client
        self._batch = Batch(client)
        self._batch.begin()

    def __enter__(self):
        self._client._push_batch(self._batch)
        return self._batch

    def __exit__(self, *args):
        self._client._pop_batch()


class _NoCommitTransaction(object):

    def __init__(self, client, transaction_id='TRANSACTION'):
        from google.cloud.datastore.batch import Batch
        from google.cloud.datastore.transaction import Transaction

        self._client = client
        xact = self._transaction = Transaction(client)
        xact._id = transaction_id
        Batch.begin(xact)

    def __enter__(self):
        self._client._push_batch(self._transaction)
        return self._transaction

    def __exit__(self, *args):
        self._client._pop_batch()


class _Entity(dict):
    key = None
    exclude_from_indexes = ()
    _meanings = {}


class _Key(object):
    _MARKER = object()
    _kind = 'KIND'
    _key = 'KEY'
    _path = None
    _id = 1234
    _stored = None

    def __init__(self, project):
        self.project = project

    @property
    def is_partial(self):
        return self._id is None

    def to_protobuf(self):
        from google.cloud.proto.datastore.v1 import entity_pb2

        key = self._key = entity_pb2.Key()
        # Don't assign it, because it will just get ripped out
        # key.partition_id.project_id = self.project

        element = key.path.add()
        element.kind = self._kind
        if self._id is not None:
            element.id = self._id

        return key

    def completed_key(self, new_id):
        assert self.is_partial
        new_key = self.__class__(self.project)
        new_key._id = new_id
        return new_key


class _PathElementPB(object):

    def __init__(self, id_):
        self.id = id_


class _KeyPB(object):

    def __init__(self, id_):
        self.path = [_PathElementPB(id_)]


def _assert_num_mutations(test_case, mutation_pb_list, num_mutations):
    test_case.assertEqual(len(mutation_pb_list), num_mutations)


def _mutated_pb(test_case, mutation_pb_list, mutation_type):
    # Make sure there is only one mutation.
    _assert_num_mutations(test_case, mutation_pb_list, 1)

    # We grab the only mutation.
    mutated_pb = mutation_pb_list[0]
    # Then check if it is the correct type.
    test_case.assertEqual(mutated_pb.WhichOneof('operation'),
                          mutation_type)

    return getattr(mutated_pb, mutation_type)


def _make_key(id_):
    from google.cloud.proto.datastore.v1 import entity_pb2

    key = entity_pb2.Key()
    elem = key.path.add()
    elem.id = id_
    return key
