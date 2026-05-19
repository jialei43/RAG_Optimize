"""配置模块单元测试"""
import pytest  # pytest 测试框架
from app import config  # 被测模块


class TestMySQLConfig:
    def test_host_not_empty(self):
        assert config.mysql.host  # host 必须有值

    def test_user_is_edu_rag(self):
        assert config.mysql.user == "edu_rag"  # 用户名与 config.ini 一致

    def test_database_is_subjects_kg(self):
        assert config.mysql.database == "subjects_kg"  # 数据库名与 config.ini 一致


class TestRedisConfig:
    def test_port_default(self):
        assert config.redis.port == 6379  # Redis 默认端口

    def test_db_is_zero(self):
        assert config.redis.db == 0  # 使用 db0


class TestMilvusConfig:
    def test_port_default(self):
        assert config.milvus.port == 19530  # Milvus 默认端口

    def test_database_name(self):
        assert config.milvus.database_name == "itcast"

    def test_collection_name(self):
        assert config.milvus.collection_name == "edurag_bj29"


class TestLLMConfig:
    def test_model_name(self):
        assert config.llm.model == "qwen-3.6"  # 与 config.ini 一致

    def test_base_url_not_empty(self):
        assert config.llm.base_url.startswith("https://")  # URL 格式合法


class TestRetrievalConfig:
    def test_parent_chunk_size(self):
        assert config.retrieval.parent_chunk_size == 1200

    def test_child_chunk_size(self):
        assert config.retrieval.child_chunk_size == 300

    def test_child_smaller_than_parent(self):
        assert config.retrieval.child_chunk_size < config.retrieval.parent_chunk_size  # 子块必须小于父块

    def test_retrieval_k(self):
        assert config.retrieval.retrieval_k == 10

    def test_candidate_m_less_than_k(self):
        assert config.retrieval.candidate_m < config.retrieval.retrieval_k  # m 必须小于 k


class TestAppConfig:
    def test_valid_sources_is_list(self):
        assert isinstance(config.app_cfg.valid_sources, list)  # 必须解析为列表

    def test_valid_sources_contains_expected(self):
        expected = {"ai", "java", "test", "ops", "bigdata"}
        assert expected == set(config.app_cfg.valid_sources)  # 学科集合完全一致

    def test_customer_service_phone(self):
        assert config.app_cfg.customer_service_phone == "10086"  # 客服热线
