import logging
from unittest.mock import Mock, call, ANY
from workers import ClusterEventsWorker, ClusterEventsWorkerConfig
from utils import ErrorCounter, Changes, get_dict_hash, get_event_id
from config import SentryConfig, EventStoreConfig
from assisted_service_client.rest import ApiException


class TestClusterEventsWorker:
    def setup(self):
        logging.disable(logging.CRITICAL)
        self.ai_client_mock = Mock()
        self.cluster_events_storage_mock = Mock()
        self.es_store = Mock()
        self.error_counter = ErrorCounter()
        self.changes = Changes()
        self.config = ClusterEventsWorkerConfig(
            1,
            SentryConfig(
                False,
                ""
            ),
            self.error_counter,
            self.changes,
            EventStoreConfig.create_from_env()
        )
        self.worker = ClusterEventsWorker(
            self.config,
            self.ai_client_mock,
            self.cluster_events_storage_mock,
            self.es_store
        )

    def teardown(self):
        self.worker = None

    def test_error_getting_cluster(self):
        self.ai_client_mock.get_cluster_hosts.side_effect = Exception("Error getting cluster's hosts")

        cluster = {"id": "abcd", "name": "mycluster", "infra_env": {"foo": "bar"}}
        self.worker.store_events_for_cluster(cluster)
        self.ai_client_mock.get_events.assert_not_called()
        self.ai_client_mock.get_versions.assert_not_called()
        self.cluster_events_storage_mock.store.assert_not_called()
        self._expect_store_normalized_events_not_called()

        assert 1 == self.error_counter.get_errors()
        assert not self.changes.has_changed_in_last_minutes(1)

    def test_cluster_not_found(self):
        self.ai_client_mock.get_cluster_hosts.side_effect = ApiException(status=404, reason="Not found")

        cluster = {"id": "abcd", "name": "mycluster", "infra_env": {"foo": "bar"}}
        self.worker.store_events_for_cluster(cluster)
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events()

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_error_getting_events(self):
        self.ai_client_mock.get_events.side_effect = Exception("Error getting cluster")

        cluster = {"id": "abcd", "name": "mycluster", "infra_env": {"foo": "bar"}}
        self.worker.store_events_for_cluster(cluster)
        self.ai_client_mock.get_cluster_hosts.assert_called_once()
        self.cluster_events_storage_mock.store.assert_not_called()
        self._expect_store_normalized_events_not_called()

        assert 1 == self.error_counter.get_errors()
        assert not self.changes.has_changed_in_last_minutes(1)

    def test_events_not_found(self):
        self.ai_client_mock.get_events.side_effect = ApiException(status=404, reason="Not found")

        cluster = {"id": "abcd", "name": "mycluster", "infra_env": {"foo": "bar"}}
        self.worker.store_events_for_cluster(cluster)
        self.ai_client_mock.get_cluster_hosts.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events()

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_error_storing_events(self):
        self.cluster_events_storage_mock.store.side_effect = Exception("Error getting cluster")

        cluster = {"id": "abcd", "name": "mycluster", "infra_env": {"foo": "bar"}}
        self.worker.store_events_for_cluster(cluster)
        self.ai_client_mock.get_cluster_hosts.assert_called_once()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self._expect_store_normalized_events()

        assert 1 == self.error_counter.get_errors()
        assert not self.changes.has_changed_in_last_minutes(1)

    def test_error_storing_normalized_events(self):
        self.es_store.store_changes.side_effect = Exception("Error storing normalized events")

        cluster = {"id": "abcd", "name": "mycluster", "infra_env": {"foo": "bar"}}
        self.worker.store_events_for_cluster(cluster)
        self.ai_client_mock.get_cluster_hosts.assert_called_once()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()

        assert 1 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_storing_events(self):

        cluster = {"id": "abcd", "name": "mycluster", "infra_env": {"foo": "bar"}}

        self.worker.store_events_for_cluster(cluster)

        self.ai_client_mock.get_cluster_hosts.assert_called_once()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events()

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_storing_events_cluster_with_hosts(self):

        cluster = {"id": "abcd", "name": "mycluster", "hosts": ["1", "2", "3"], "infra_env": {"foo": "bar"}}

        self.worker.store_events_for_cluster(cluster)

        self.ai_client_mock.get_cluster_hosts.assert_not_called()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events()

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_storing_events_cluster_with_empty_infraenv(self):

        cluster = {"id": "abcd", "name": "mycluster", "hosts": ["1", "2", "3"], "infra_env": {}}

        self.worker.store_events_for_cluster(cluster)

        self.ai_client_mock.get_cluster_hosts.assert_not_called()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events(no_infraenv=True)

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_storing_events_cluster_with_no_infraenv(self):
        cluster = {"id": "abcd", "name": "mycluster", "hosts": ["1", "2", "3"]}

        self.worker.store_events_for_cluster(cluster)

        self.ai_client_mock.get_cluster_hosts.assert_not_called()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events(no_infraenv=True)

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_storing_events_cluster_with_empty_hosts(self):
        cluster = {"id": "abcd", "name": "mycluster", "hosts": [], "infra_env": {"foo": "bar"}}

        self.worker.store_events_for_cluster(cluster)

        self.ai_client_mock.get_cluster_hosts.assert_called_once()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events()

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def test_process_clusters(self):
        clusters = [{"id": "abcd", "name": "mycluster", "hosts": [], "infra_env": {"foo": "bar"}}]
        infraenvs = [
            {
                "kind": "InfraEnv",
                "href": "foobar",
                "cluster_id": "abcd",
                "type": "full-iso",
                "id": "12345",
                "name": "foo",
                "created_at": "2022-01-01",
                "updated_at": "2022-01-01",
            },
            {
                "kind": "InfraEnv",
                "cluster_id": "cdef",
                "href": "foobar",
                "id": "67890",
                "type": "minimal-iso",
                "name": "bar",
                "created_at": "2022-01-01",
                "updated_at": "2022-01-01",
            },
        ]

        self.worker.process_clusters(clusters, infraenvs)

        self.ai_client_mock.get_cluster_hosts.assert_called_once()
        self.ai_client_mock.get_events.assert_called_once()
        self.ai_client_mock.get_versions.assert_called_once()
        self.cluster_events_storage_mock.store.assert_called_once()
        self._expect_store_normalized_events()

        assert 0 == self.error_counter.get_errors()
        assert self.changes.has_changed_in_last_minutes(1)

    def _expect_store_normalized_events(self, no_infraenv=False):
        expected_calls = []
        if not no_infraenv:
            expected_calls = [call(index=self.config.events.infra_envs_events_index, filter_by=ANY,
                                   documents=ANY, id_fn=get_dict_hash)]

        expected_calls += [
            call(index=self.config.events.component_versions_events_index,
                 documents=ANY, id_fn=ANY, transform_document_fn=ANY),
            call(index=self.config.events.cluster_events_index, filter_by=ANY,
                 documents=ANY, id_fn=ANY),
            call(index=self.config.events.events_index, documents=ANY, filter_by=ANY,
                 id_fn=get_event_id),
        ]
        self.es_store.store_changes.assert_has_calls(expected_calls)

    def _expect_store_normalized_events_not_called(self):
        self.es_store.store_changes.assert_not_called()
