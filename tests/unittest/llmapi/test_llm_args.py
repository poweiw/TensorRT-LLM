import tempfile

import pydantic_core
import pytest
import yaml

import tensorrt_llm.bindings.executor as tle
from tensorrt_llm import LLM as TorchLLM
from tensorrt_llm import AutoParallelConfig
from tensorrt_llm._tensorrt_engine import LLM
from tensorrt_llm.builder import LoraConfig
from tensorrt_llm.llmapi import (BuildConfig, CapacitySchedulerPolicy,
                                 SchedulerConfig)
from tensorrt_llm.llmapi.llm_args import *
from tensorrt_llm.llmapi.utils import print_traceback_on_error
from tensorrt_llm.plugin import PluginConfig

from .test_llm import llama_model_path


def test_LookaheadDecodingConfig():
    # from constructor
    config = LookaheadDecodingConfig(max_window_size=4,
                                     max_ngram_size=3,
                                     max_verification_set_size=4)
    assert config.max_window_size == 4
    assert config.max_ngram_size == 3
    assert config.max_verification_set_size == 4

    # from dict
    config = LookaheadDecodingConfig.from_dict({
        "max_window_size": 4,
        "max_ngram_size": 3,
        "max_verification_set_size": 4
    })
    assert config.max_window_size == 4
    assert config.max_ngram_size == 3
    assert config.max_verification_set_size == 4

    # to pybind
    pybind_config = config._to_pybind()
    assert isinstance(pybind_config, tle.LookaheadDecodingConfig)
    assert pybind_config.max_window_size == 4
    assert pybind_config.max_ngram_size == 3
    assert pybind_config.max_verification_set_size == 4


class TestYaml:

    def _yaml_to_dict(self, yaml_content: str) -> dict:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(yaml_content.encode('utf-8'))
            f.flush()
            f.seek(0)
            dict_content = yaml.safe_load(f)
        return dict_content

    def test_update_llm_args_with_extra_dict_with_speculative_config(self):
        yaml_content = """
speculative_config:
    decoding_type: Lookahead
    max_window_size: 4
    max_ngram_size: 3
    verification_set_size: 4
    """
        dict_content = self._yaml_to_dict(yaml_content)

        llm_args = TrtLlmArgs(model=llama_model_path)
        llm_args_dict = update_llm_args_with_extra_dict(llm_args.to_dict(),
                                                        dict_content)
        llm_args = TrtLlmArgs(**llm_args_dict)
        assert llm_args.speculative_config.max_window_size == 4
        assert llm_args.speculative_config.max_ngram_size == 3
        assert llm_args.speculative_config.max_verification_set_size == 4

    def test_llm_args_with_invalid_yaml(self):
        yaml_content = """
pytorch_backend_config: # this is deprecated
    max_num_tokens: 1
    max_seq_len: 1
"""
        dict_content = self._yaml_to_dict(yaml_content)

        llm_args = TrtLlmArgs(model=llama_model_path)
        llm_args_dict = update_llm_args_with_extra_dict(llm_args.to_dict(),
                                                        dict_content)
        with pytest.raises(ValueError):
            llm_args = TrtLlmArgs(**llm_args_dict)

    def test_llm_args_with_build_config(self):
        # build_config isn't a Pydantic
        yaml_content = """
build_config:
    max_beam_width: 4
    max_batch_size: 8
    max_num_tokens: 256
    """
        dict_content = self._yaml_to_dict(yaml_content)

        llm_args = TrtLlmArgs(model=llama_model_path)
        llm_args_dict = update_llm_args_with_extra_dict(llm_args.to_dict(),
                                                        dict_content)
        llm_args = TrtLlmArgs(**llm_args_dict)
        assert llm_args.build_config.max_beam_width == 4
        assert llm_args.build_config.max_batch_size == 8
        assert llm_args.build_config.max_num_tokens == 256

    def test_llm_args_with_kvcache_config(self):
        yaml_content = """
kv_cache_config:
    enable_block_reuse: True
    max_tokens: 1024
    max_attention_window: [1024, 1024, 1024]
    """
        dict_content = self._yaml_to_dict(yaml_content)

        llm_args = TrtLlmArgs(model=llama_model_path)
        llm_args_dict = update_llm_args_with_extra_dict(llm_args.to_dict(),
                                                        dict_content)
        llm_args = TrtLlmArgs(**llm_args_dict)
        assert llm_args.kv_cache_config.enable_block_reuse == True
        assert llm_args.kv_cache_config.max_tokens == 1024
        assert llm_args.kv_cache_config.max_attention_window == [
            1024, 1024, 1024
        ]

    def test_llm_args_with_pydantic_options(self):
        yaml_content = """
max_batch_size: 16
max_num_tokens: 256
max_seq_len: 128
    """
        dict_content = self._yaml_to_dict(yaml_content)

        llm_args = TrtLlmArgs(model=llama_model_path)
        llm_args_dict = update_llm_args_with_extra_dict(llm_args.to_dict(),
                                                        dict_content)
        llm_args = TrtLlmArgs(**llm_args_dict)
        assert llm_args.max_batch_size == 16
        assert llm_args.max_num_tokens == 256
        assert llm_args.max_seq_len == 128


def check_defaults(py_config_cls, pybind_config_cls):
    py_config = py_config_cls()
    pybind_config = pybind_config_cls()
    # get member variables from pybinding_config
    for member in PybindMirror.get_pybind_variable_fields(pybind_config_cls):
        py_value = getattr(py_config, member)
        pybind_value = getattr(pybind_config, member)
        assert py_value == pybind_value, f"{member} default value is not equal"


def test_KvCacheConfig_declaration():
    config = KvCacheConfig(enable_block_reuse=True,
                           max_tokens=1024,
                           max_attention_window=[1024, 1024, 1024],
                           sink_token_length=32,
                           free_gpu_memory_fraction=0.5,
                           host_cache_size=1024,
                           onboard_blocks=True,
                           cross_kv_cache_fraction=0.5,
                           secondary_offload_min_priority=1,
                           event_buffer_max_size=0,
                           enable_partial_reuse=True,
                           copy_on_partial_reuse=True)

    pybind_config = config._to_pybind()
    assert pybind_config.enable_block_reuse == True
    assert pybind_config.max_tokens == 1024
    assert pybind_config.max_attention_window == [1024, 1024, 1024]
    assert pybind_config.sink_token_length == 32
    assert pybind_config.free_gpu_memory_fraction == 0.5
    assert pybind_config.host_cache_size == 1024
    assert pybind_config.onboard_blocks == True
    assert pybind_config.cross_kv_cache_fraction == 0.5
    assert pybind_config.secondary_offload_min_priority == 1
    assert pybind_config.event_buffer_max_size == 0
    assert pybind_config.enable_partial_reuse == True
    assert pybind_config.copy_on_partial_reuse == True


def test_KvCacheConfig_default_values():
    check_defaults(KvCacheConfig, tle.KvCacheConfig)


def test_CapacitySchedulerPolicy():
    val = CapacitySchedulerPolicy.MAX_UTILIZATION
    assert PybindMirror.maybe_to_pybind(
        val) == tle.CapacitySchedulerPolicy.MAX_UTILIZATION


def test_ContextChunkingPolicy():
    val = ContextChunkingPolicy.EQUAL_PROGRESS
    assert PybindMirror.maybe_to_pybind(
        val) == tle.ContextChunkingPolicy.EQUAL_PROGRESS


def test_DynamicBatchConfig_declaration():
    config = DynamicBatchConfig(enable_batch_size_tuning=True,
                                enable_max_num_tokens_tuning=True,
                                dynamic_batch_moving_average_window=10)

    pybind_config = PybindMirror.maybe_to_pybind(config)

    assert pybind_config.enable_batch_size_tuning == True
    assert pybind_config.enable_max_num_tokens_tuning == True
    assert pybind_config.dynamic_batch_moving_average_window == 10


def test_SchedulerConfig_declaration():
    config = SchedulerConfig(
        capacity_scheduler_policy=CapacitySchedulerPolicy.MAX_UTILIZATION,
        context_chunking_policy=ContextChunkingPolicy.EQUAL_PROGRESS,
        dynamic_batch_config=DynamicBatchConfig(
            enable_batch_size_tuning=True,
            enable_max_num_tokens_tuning=True,
            dynamic_batch_moving_average_window=10))

    pybind_config = PybindMirror.maybe_to_pybind(config)
    assert pybind_config.capacity_scheduler_policy == tle.CapacitySchedulerPolicy.MAX_UTILIZATION
    assert pybind_config.context_chunking_policy == tle.ContextChunkingPolicy.EQUAL_PROGRESS
    assert PybindMirror.pybind_equals(pybind_config.dynamic_batch_config,
                                      config.dynamic_batch_config._to_pybind())


def test_PeftCacheConfig_default_values():
    check_defaults(PeftCacheConfig, tle.PeftCacheConfig)


def test_PeftCacheConfig_declaration():
    config = PeftCacheConfig(num_host_module_layer=1,
                             num_device_module_layer=1,
                             optimal_adapter_size=64,
                             max_adapter_size=128,
                             num_put_workers=1,
                             num_ensure_workers=1,
                             num_copy_streams=1,
                             max_pages_per_block_host=24,
                             max_pages_per_block_device=8,
                             device_cache_percent=0.5,
                             host_cache_size=1024,
                             lora_prefetch_dir=".")

    pybind_config = PybindMirror.maybe_to_pybind(config)
    assert pybind_config.num_host_module_layer == 1
    assert pybind_config.num_device_module_layer == 1
    assert pybind_config.optimal_adapter_size == 64
    assert pybind_config.max_adapter_size == 128
    assert pybind_config.num_put_workers == 1
    assert pybind_config.num_ensure_workers == 1
    assert pybind_config.num_copy_streams == 1
    assert pybind_config.max_pages_per_block_host == 24
    assert pybind_config.max_pages_per_block_device == 8
    assert pybind_config.device_cache_percent == 0.5
    assert pybind_config.host_cache_size == 1024
    assert pybind_config.lora_prefetch_dir == "."


def test_update_llm_args_with_extra_dict_with_nested_dict():
    llm_api_args_dict = {
        "model":
        "dummy-model",
        "build_config":
        None,  # Will override later.
        "extended_runtime_perf_knob_config":
        ExtendedRuntimePerfKnobConfig(multi_block_mode=True),
        "kv_cache_config":
        KvCacheConfig(enable_block_reuse=False),
        "peft_cache_config":
        PeftCacheConfig(num_host_module_layer=0),
        "scheduler_config":
        SchedulerConfig(capacity_scheduler_policy=CapacitySchedulerPolicy.
                        GUARANTEED_NO_EVICT)
    }
    plugin_config_dict = {
        "_dtype": 'float16',
        "nccl_plugin": None,
    }
    plugin_config = PluginConfig.from_dict(plugin_config_dict)
    build_config = BuildConfig(max_input_len=1024,
                               lora_config=LoraConfig(lora_ckpt_source='hf'),
                               auto_parallel_config=AutoParallelConfig(
                                   world_size=1,
                                   same_buffer_io={},
                                   debug_outputs=[]),
                               plugin_config=plugin_config)
    extra_llm_args_dict = {
        "build_config": build_config.to_dict(),
    }

    llm_api_args_dict = update_llm_args_with_extra_dict(llm_api_args_dict,
                                                        extra_llm_args_dict,
                                                        "build_config")
    initialized_llm_args = TrtLlmArgs(**llm_api_args_dict)

    def check_nested_dict_equality(dict1, dict2, path=""):
        if not isinstance(dict1, dict) or not isinstance(dict2, dict):
            if dict1 != dict2:
                raise ValueError(f"Mismatch at {path}: {dict1} != {dict2}")
            return True
        if dict1.keys() != dict2.keys():
            raise ValueError(f"Different keys at {path}:")
        for key in dict1:
            new_path = f"{path}.{key}" if path else key
            if not check_nested_dict_equality(dict1[key], dict2[key], new_path):
                raise ValueError(f"Mismatch at {path}: {dict1} != {dict2}")
        return True

    build_config_dict1 = build_config.to_dict()
    build_config_dict2 = initialized_llm_args.build_config.to_dict()
    check_nested_dict_equality(build_config_dict1, build_config_dict2)


class TestTorchLlmArgsCudaGraphSettings:

    def test_cuda_graph_batch_sizes_case_0(self):
        # set both cuda_graph_batch_sizes and cuda_graph_config.max_batch_size, and
        # cuda_graph_batch_sizes is not equal to generated
        with pytest.raises(ValueError):
            TorchLlmArgs(
                model=llama_model_path,
                cuda_graph_config=CudaGraphConfig(batch_sizes=[1, 2, 3],
                                                  max_batch_size=128),
            )

    def test_cuda_graph_batch_sizes_case_0_1(self):
        # set both cuda_graph_batch_sizes and cuda_graph_config.max_batch_size, and
        # cuda_graph_batch_sizes is equal to generated
        args = TorchLlmArgs(
            model=llama_model_path,
            cuda_graph_config=CudaGraphConfig(
                batch_sizes=CudaGraphConfig._generate_cuda_graph_batch_sizes(
                    128, True),
                enable_padding=True,
                max_batch_size=128))
        assert args.cuda_graph_config.batch_sizes == CudaGraphConfig._generate_cuda_graph_batch_sizes(
            128, True)
        assert args.cuda_graph_config.max_batch_size == 128

    def test_cuda_graph_batch_sizes_case_1(self):
        # set cuda_graph_batch_sizes only
        args = TorchLlmArgs(model=llama_model_path,
                            cuda_graph_config=CudaGraphConfig(
                                batch_sizes=[1, 2, 4], enable_padding=True))
        assert args.cuda_graph_config.batch_sizes == [1, 2, 4]

    def test_cuda_graph_batch_sizes_case_2(self):
        # set cuda_graph_config.max_batch_size only
        args = TorchLlmArgs(model=llama_model_path,
                            cuda_graph_config=CudaGraphConfig(
                                max_batch_size=128, enable_padding=True))
        assert args.cuda_graph_config.batch_sizes == CudaGraphConfig._generate_cuda_graph_batch_sizes(
            128, True)
        assert args.cuda_graph_config.max_batch_size == 128


class TestTrtLlmArgs:

    def test_dynamic_setattr(self):
        with pytest.raises(pydantic_core._pydantic_core.ValidationError):
            args = TrtLlmArgs(model=llama_model_path, invalid_arg=1)

        with pytest.raises(ValueError):
            args = TrtLlmArgs(model=llama_model_path)
            args.invalid_arg = 1


class TestTorchLlmArgs:

    @print_traceback_on_error
    def test_runtime_sizes(self):
        llm = TorchLLM(
            llama_model_path,
            max_beam_width=1,
            max_num_tokens=256,
            max_seq_len=128,
            max_batch_size=8,
        )

        assert llm.args.max_beam_width == 1
        assert llm.args.max_num_tokens == 256
        assert llm.args.max_seq_len == 128
        assert llm.args.max_batch_size == 8

        assert llm._executor_config.max_beam_width == 1
        assert llm._executor_config.max_num_tokens == 256
        assert llm._executor_config.max_seq_len == 128
        assert llm._executor_config.max_batch_size == 8

    def test_dynamic_setattr(self):
        with pytest.raises(pydantic_core._pydantic_core.ValidationError):
            args = TorchLlmArgs(model=llama_model_path, invalid_arg=1)

        with pytest.raises(ValueError):
            args = TorchLlmArgs(model=llama_model_path)
            args.invalid_arg = 1

    def test_from_build_config(self):
        build_config = BuildConfig(
            max_beam_width=4,
            max_batch_size=8,
            max_num_tokens=256,
        )
        args = TorchLlmArgs.from_kwargs(model=llama_model_path,
                                        build_config=build_config)

        assert args.max_batch_size == build_config.max_batch_size
        assert args.max_num_tokens == build_config.max_num_tokens
        assert args.max_beam_width == build_config.max_beam_width


class TestTrtLlmArgs:

    def test_build_config_default(self):
        args = TrtLlmArgs(model=llama_model_path)
        # It will create a default build_config
        assert args.build_config
        assert args.build_config.max_beam_width == 1

    def test_build_config_change(self):
        build_config = BuildConfig(
            max_beam_width=4,
            max_batch_size=8,
            max_num_tokens=256,
        )
        args = TrtLlmArgs(model=llama_model_path, build_config=build_config)
        assert args.build_config.max_beam_width == build_config.max_beam_width
        assert args.build_config.max_batch_size == build_config.max_batch_size
        assert args.build_config.max_num_tokens == build_config.max_num_tokens

    def test_LLM_with_build_config(self):
        build_config = BuildConfig(
            max_beam_width=4,
            max_batch_size=8,
            max_num_tokens=256,
        )
        args = TrtLlmArgs(model=llama_model_path, build_config=build_config)

        assert args.build_config.max_beam_width == build_config.max_beam_width
        assert args.build_config.max_batch_size == build_config.max_batch_size
        assert args.build_config.max_num_tokens == build_config.max_num_tokens

        assert args.max_beam_width == build_config.max_beam_width

    def test_to_dict_and_from_dict(self):
        build_config = BuildConfig(
            max_beam_width=4,
            max_batch_size=8,
            max_num_tokens=256,
        )
        args = TrtLlmArgs(model=llama_model_path, build_config=build_config)
        args_dict = args.to_dict()

        new_args = TrtLlmArgs.from_kwargs(**args_dict)

        assert new_args.to_dict() == args_dict

    def test_build_config_from_engine(self):
        build_config = BuildConfig(max_batch_size=8, max_num_tokens=256)
        tmp_dir = tempfile.mkdtemp()
        with LLM(model=llama_model_path, build_config=build_config) as llm:
            llm.save(tmp_dir)

        args = TrtLlmArgs(
            model=tmp_dir,
            # runtime values
            max_num_tokens=16,
            max_batch_size=4,
        )
        assert args.build_config.max_batch_size == build_config.max_batch_size
        assert args.build_config.max_num_tokens == build_config.max_num_tokens

        assert args.max_num_tokens == 16
        assert args.max_batch_size == 4
