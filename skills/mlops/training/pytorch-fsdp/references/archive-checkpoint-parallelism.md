## Distributed Checkpoint - torch.distributed.checkpoint#

**URL:** https://pytorch.org/docs/stable/distributed.checkpoint.html

**Contents:**
- Distributed Checkpoint - torch.distributed.checkpoint#
- Additional resources:#

Created On: Nov 16, 2022 | Last Updated On: Sep 04, 2025

Distributed Checkpoint (DCP) support loading and saving models from multiple ranks in parallel. It handles load-time resharding which enables saving in one cluster topology and loading into another.

DCP is different than torch.save and torch.load in a few significant ways:

It produces multiple files per checkpoint, with at least one per rank.

It operates in place, meaning that the model should allocate its data first and DCP uses that storage instead.

The entrypoints to load and save a checkpoint are the following:

Getting Started with Distributed Checkpoint (DCP)

Asynchronous Saving with Distributed Checkpoint (DCP)

TorchTitan Checkpointing Docs

TorchTitan DCP Implementation

Enum for async checkpointer type.

This class contains futures for staging and upload completion. It is returned by async_save(). staging_completion is a future that indicates when local copy of state_dict is complete. upload_completion is a future that indicates when a checkpoint completed saving.

Save a distributed model in SPMD style.

This function is different from torch.save() as it handles ShardedTensor , and DTensor by having each rank only save their local shards.

For each Stateful object (having both a state_dict and a load_state_dict), save will call state_dict before serialization.

There is no guarantees of Backwards Compatibility across PyTorch versions for saved state_dicts.

If using the process_group argument, make sure that only its ranks call save_state_dict and that all data in state_dict belong to it.

When saving checkpoint for FSDP’s ShardingStrategy.HYBRID_SHARD, only one of the shard_group should be calling save_state_dict and the corresponding process group needs to be passed in.

state_dict in the local process.

state_dict (Dict[str, Any]) – The state_dict to save.

checkpoint_id (Union[str, os.PathLike, None]) – The ID of this checkpoint instance. The meaning of the checkpoint_id depends on the storage. It can be a path to a folder or to a file. It can also be a key if the storage is a key-value store. (Default: None)

storage_writer (Optional[StorageWriter]) – Instance of StorageWriter used to perform writes. If this is not specified, DCP will automatically infer the writer based on the checkpoint_id. If checkpoint_id is also None, an exception will be raised. (Default: None)

planner (Optional[SavePlanner]) – Instance of SavePlanner. If this is not specified, the default planner will be used. (Default: None)

process_group (Optional[ProcessGroup]) – ProcessGroup to be used for cross-rank synchronization. (Default: None)

no_dist (bool) – If True, this function will assume the intent is to load a checkpoint on a single rank/process. (Default: False)

use_collectives (bool) – If False, this function will assume the intent is to save a checkpoint without using cross-rank synchronization. (Default: True) This configuration is experimental and should be used with caution. It will change the format of the saved checkpoint and may not be backward compatible.

Metadata object for the saved checkpoint.

save_state_dict uses collectives to coordinate writes across ranks. For NCCL-based process groups, internal tensor representations of objects must be moved to the GPU device before communication takes place. In this case, the device used is given by torch.cuda.current_device() and it is the user’s responsibility to ensure that this is set so that each rank has an individual GPU, via torch.cuda.set_device().

Asynchronous version of save. This code first de-stages the state_dict on to the staging storage (defaults to CPU memory), and then calls the save in a separate thread.

This feature is experimental and subject to change. MUST CALL CLOSE AFTER LAST CHECKPOINT IS SAVED

state_dict (Dict[str, Any]) – The state_dict to save.

checkpoint_id (Union[str, os.PathLike, None]) – The ID of this checkpoint instance. The meaning of the checkpoint_id depends on the storage. It can be a path to a folder or to a file. It can also be a key if the storage is a key-value store. (Default: None)

storage_writer (Optional[StorageWriter]) – Instance of StorageWriter used to perform ‘stage’ and ‘save’. If this is not specified, DCP will automatically infer the writer based on the checkpoint_id. If checkpoint_id is also None, an exception will be raised. (Default: None)

planner (Optional[SavePlanner]) – Instance of SavePlanner. If this is not specified, the default planner will be used. (Default: None)

process_group (Optional[ProcessGroup]) – ProcessGroup to be used for cross-rank synchronization. (Default: None)

async_checkpointer_type (AsyncCheckpointerType) – whether to do checkpoint in separate thread or process (Default: AsyncCheckpointerType.THREAD)

async_stager (AsyncStager) – provides staging implementation. If storage_writer implements AsyncStager and async_stager is provided, async_stager will be used for staging

no_dist (bool) – If True, this function will assume the intent is to save a checkpoint on a single rank/process. (Default: False)

use_collectives (bool) – If False, Save the checkpoint without rank coordination. (Default: True) This configuration is experimental and should be used with caution. It will change the format of the saved checkpoint and may not be backward compatible.

A future holding the resultant Metadata object from save.

This method is deprecated. Please switch to ‘save’.

Load a checkpoint into a distributed state dict in SPMD style.

Each rank must have the same keys in their state_dict provided to this API. Mismatched keys may result in hangs or errors. If unsure, you can use the utils._assert_same_keys API to check (but may incur communication costs).

Each rank will try to read the least amount of data necessary to fulfill the requested state_dict. When loading ShardedTensor or DTensor instances, each rank only reads data for their local shards.

For each Stateful object (having both a state_dict and a load_state_dict), load will first call state_dict before attempting deserialization, followed by load_state_dict once the deserialization is complete. For each non-Stateful object, load will deserialize the object, and then replace it in the state_dict with the deserialized object.

All tensors in state_dict must be allocated on their destination device prior to calling this function.

All non-tensor data is loaded using torch.load() and modified in place on state_dict.

Users must call load_state_dict on the root module to ensure load pos-processing and non-tensor data properly propagates.

state_dict (Dict[str, Any]) – The state_dict to load the checkpoint into.

checkpoint_id (Union[str, os.PathLike, None]) – The ID of this checkpoint instance. The meaning of the checkpoint_id depends on the storage. It can be a path to a folder or to a file. It can also be a key if the storage is a key-value store. (Default: None)

storage_reader (Optional[StorageReader]) – Instance of StorageWriter used to perform reads. If this is not specified, DCP will automatically infer the reader based on the checkpoint_id. If checkpoint_id is also None, an exception will be raised. (Default: None)

planner (Optional[LoadPlanner]) – Instance of LoadPlanner. If this is not specified, the default planner will be used. (Default: None)

process_group (Optional[ProcessGroup]) – ProcessGroup to be used for cross-rank synchronization. (Default: None)

no_dist (bool) – If True, this function will assume the intent is to load a checkpoint without using cross-rank synchronization. (Default: False)

load_state_dict uses collectives to coordinate reads across ranks. For NCCL-based process groups, internal tensor representations of objects must be moved to the GPU device before communication takes place. In this case, the device used is given by torch.cuda.current_device() and it is the user’s responsibility to ensure that this is set so that each rank has an individual GPU, via torch.cuda.set_device().

This method is deprecated. Please switch to ‘load’.

The following module is also useful for additional customization of the staging mechanisms used for asynchronous checkpointing (torch.distributed.checkpoint.async_save):

This protocol is meant to provide customization and extensibility for dcp.async_save, allowing users to customize how data is staged previous to executing the usual dcp.save path in parallel. The expected order of operations (concretely defined in torch.distributed.state_dict_saver.async_save) is the following:

This call gives the AsyncStager the opportunity to ‘stage’ the state_dict. The expectation and purpose of staging in this context is to create a “training-safe” representation of the state dict, meaning that any updates to module data after staging is complete should not be reflected in the state dict returned from this method. For example, in the default case a copy of the entire state dict is created on CPU RAM and returned here, allowing users to continue training without risking changes to data which is being serialized.

for serializing the state_dict and writing it to storage.

the serialization thread starts and before returning from dcp.async_save. If this is set to False, the assumption is the user has defined a custom synchronization point for the purpose of further optimizing save latency in the training loop (for example, by overlapping staging with the forward/backward pass), and it is the respondsibility of the user to call AsyncStager.synchronize_staging at the appropriate time.

Clean up all resources used by the stager.

Whether to synchronize after executing the stage.

Returns a “staged” copy of state_dict. The expectation of the staged copy is that it is inoculated from any updates incurred after the stage call is complete.

Union[Future[dict[str, Union[~StatefulT, Any]]], dict[str, Union[~StatefulT, Any]]]

In the case stage is async in some way, this method should be called to ensure staging is complete and it is safe to begin modifying the original state_dict

DefaultStager provides a full-featured staging implementation that combines multiple optimization techniques for efficient checkpoint preparation.

The staging process works as follows: 1. State dictionary is submitted for staging (sync or async) 2. Tensors are copied from GPU to optimized CPU storage 3. CUDA operations are synchronized if non-blocking copies are used 4. Staged state dictionary is returned or made available via Future

# Synchronous staging stager = DefaultStager(StagingOptions(use_async_staging=False)) staged_dict = stager.stage(state_dict) stager.close()

# Asynchronous staging stager = DefaultStager(StagingOptions(use_async_staging=True)) future = stager.stage(state_dict) # … do other work … staged_dict = future.result() stager.close()

# Context manager pattern (recommended) stager = DefaultStager(config) with stager: result = stager.stage(state_dict)

Async staging provides best performance when model computation can overlap with staging operations

Pinned memory improves CPU-GPU transfer speeds but uses more memory

Shared memory allows efficient IPC to checkpoint process

Non-blocking copies reduce GPU idle time during memory transfers

DefaultStager is not thread-safe. Each thread should use its own instance, or external synchronization should be provided.

Clean up all resources used by the DefaultStager. Shuts down the ThreadPoolExecutor used for async staging operations and cleans up the underlying StateDictStager’s cached storages. Should be called when the stager is no longer needed to prevent resource leaks, especially in long-running applications. After calling close(), the stager should not be used for further staging operations.

stager = DefaultStager(StagingOptions(use_async_staging=True)) future = stager.stage(state_dict) result = future.result() stager.close() # Clean up all resources

This function is responsible for staging staging the state_dict. See class docstring for more details on staging. If use_async_staging is True, it will return a Future object that will be fulfilled when staging is complete. If use_async_staging is False, it will return the fully staged state_dict.

state_dict (STATE_DICT_TYPE) – The state_dict to be staged.

Union[dict[str, Union[~StatefulT, Any]], Future[dict[str, Union[~StatefulT, Any]]]]

When use_async_staging is True, this method will wait until staging is complete. If use_async_staging is False, this method is a no-op.

Configuration options for checkpoint staging behavior.

use_pinned_memory (bool) – Enable pinned memory allocation for faster CPU-GPU transfers. Requires CUDA to be available. Default: True

use_shared_memory (bool) – Enable shared memory for multi-process scenarios. Useful when multiple processes need access to the same staged data. Default: True

use_async_staging (bool) – Enable asynchronous staging using a background thread pool. Allows overlapping computation with staging operations. Requires CUDA. Default: True

use_non_blocking_copy (bool) – Use non-blocking device memory copies with stream synchronization. Improves performance by allowing CPU work to continue during GPU transfers. Default: True

CUDA-dependent features will raise exception if CUDA is not available.

An implementation of AsyncStager which stages the state_dict on CPU RAM and blocks until the copy is complete. This implementation also provides an option to optimize stage latency using pinned memory.

N.B. synchronize_staging is a no-op in this case.

Returns a copy of state_dict on the CPU.

dict[str, Union[~StatefulT, Any]]

No-op function, since staging is blocking.

In addition to the above entrypoints, Stateful objects, as described below, provide additional customization during saving/loading

Stateful protocol for objects that can be checkpointed and restored.

Restore the object’s state from the provided state_dict.

state_dict (dict[str, Any]) – The state dict to restore from

Objects should return their state_dict representation as a dictionary. The output of this function will be checkpointed, and later restored in load_state_dict().

Because of the inplace nature of restoring a checkpoint, this function is also called during torch.distributed.checkpoint.load.

The objects state dict

This example shows how to use Pytorch Distributed Checkpoint to save a FSDP model.

The following types define the IO interface used during checkpoint:

Interface used by load_state_dict to read from storage.

One StorageReader instance acts as both the coordinator and the follower in a distributed checkpoint. As part of initialization, each instance is told its role.

A subclass should expected the following sequence of calls by load_state_dict:

(all ranks) set checkpoint_id if users pass a valid checkpoint_id.

(all ranks) read_metadata()

(all ranks) set_up_storage_reader()

(all ranks) prepare_local_plan()

(coordinator) prepare_global_plan()

(all ranks) read_data()

Perform centralized planning of storage loading.

This method is only called on the coordinator instance.

While this method can produce a completely different plan, the preferred way is to store storage specific data in LoadPlan::storage_data.

plans (list[torch.distributed.checkpoint.planner.LoadPlan]) – A list of LoadPlan instances, one for each rank.

A list of transformed LoadPlan after storage global planning

list[torch.distributed.checkpoint.planner.LoadPlan]

Perform storage-specific local planning.

While this method can produce a completely different plan, the recommended way is to store storage specific data in LoadPlan::storage_data.

plan (LoadPlan) – The local plan from the LoadPlan in use.

A transformed LoadPlan after storage local planning

Read all items from plan using planner to resolve the data.

A subclass should call LoadPlanner::load_bytes to deserialize a BytesIO object into the right place.

A subclass should call LoadPlanner::resolve_tensor to get access to the tensors that in should load data into.

It’s the StorageLayer responsibility to properly schedule any cross device copies required.

plan (LoadPlan) – The local plan to execute on

planner (LoadPlanner) – The planner object to use to resolve items.

A future that completes once all reads are finished.

Read the checkpoint metadata.

The metadata object associated with the checkpoint being loaded.

Calls to indicates a brand new checkpoint read is going to happen. A checkpoint_id may be present if users set the checkpoint_id for this checkpoint read. The meaning of the checkpoint_id is storage-dependent. It can be a path to a folder/file or a key for a key-value storage.

checkpoint_id (Union[str, os.PathLike, None]) – The ID of this checkpoint instance. The meaning of the checkpoint_id depends on the storage. It can be a path to a folder or to a file. It can also be a key if the storage is more like a key-value store. (Default: None)

Initialize this instance.

metadata (Metadata) – The metadata schema to use.

is_coordinator (bool) – Whether this instance is responsible for coordinating the checkpoint.

Check if the given checkpoint_id is supported by the storage. This allow us to enable automatic storage selection.

Interface used by save_state_dict to write to storage.

One StorageWriter instance acts as both the coordinator and the follower in a distributed checkpoint. As part of initialization, each instance is told its role.

A subclass should expect the following sequence of calls.

(all ranks) set checkpoint_id if users pass a valid checkpoint_id.

(all ranks) set_up_storage_writer()

(all ranks) prepare_local_plan()

(coordinator) prepare_global_plan()

(all ranks) write_data()

(coordinator) finish()

Write the metadata and marks the current checkpoint as successful.

The actual format/schema used for serializing metadata is an implementation detail. The only requirement is that it’s recoverable in to the same object graph.

metadata (Metadata) – metadata for the new checkpoint

results (list[list[torch.distributed.checkpoint.storage.WriteResult]]) – A list of WriteResults from all ranks.

Perform centralized planning of storage.

This method is only called on the coordinator instance.

While this method can produce a completely different plan, the preferred way is to store storage specific data in SavePlan::storage_data.

plans (list[torch.distributed.checkpoint.planner.SavePlan]) – A list of SavePlan instances, one for each rank.

A list of transformed SavePlan after storage global planning

list[torch.distributed.checkpoint.planner.SavePlan]

Perform storage-specific local planning.

While this method can produce a completely different plan, the recommended way is to store storage specific data in SavePlan::storage_data.

plan (SavePlan) – The local plan from the SavePlanner in use.

A transformed SavePlan after storage local planning

Calls to indicates a brand new checkpoint write is going to happen. A checkpoint_id may be present if users set the checkpoint_id for this checkpoint write. The meaning of the checkpoint_id is storage-dependent. It can be a path to a folder/file or a key for a key-value storage.

checkpoint_id (Union[str, os.PathLike, None]) – The ID of this checkpoint instance. The meaning of the checkpoint_id depends on the storage. It can be a path to a folder or to a file. It can also be a key if the storage is a key-value store. (Default: None)

Initialize this instance.

is_coordinator (bool) – Whether this instance is responsible for coordinating the checkpoint.

Return the storage-specific metadata. This is used to store additional information in a checkpoint that can be useful for providing request-level observability. StorageMeta is passed to the SavePlanner during save calls. Returns None by default.

Example:

```python
from torch.distributed.checkpoint.storage import StorageMeta

class CustomStorageBackend:
    def get_storage_metadata(self):
        # Return storage-specific metadata that will be stored with the checkpoint
        return StorageMeta()
```

This example shows how a storage backend can return `StorageMeta`
to attach additional metadata to a checkpoint.

Optional[StorageMeta]

Check if the given checkpoint_id is supported by the storage. This allow us to enable automatic storage selection.

Write all items from plan using planner to resolve the data.

A subclass should call SavePlanner::resolve_data on each item from the plan to get access to the underlying object to write.

Subclasses should lazily call resolve_data as it can allocate memory. In case of tensors, make following assumptions:

They might be on any device, including not matching the one on WriteItem::tensor_data

They might be views or not contiguous. Only the projection needs to be saved.

plan (SavePlan) – The save plan to execute.

planner (SavePlanner) – Planner object to be used to resolve items to data.

A future that completes to a list of WriteResult

Future[list[torch.distributed.checkpoint.storage.WriteResult]]

The following types define the planner interface used during checkpoint:

Abstract class defining the protocol used by load_state_dict to plan the load process.

LoadPlanner are stateful objects that can be used to customize the whole load process.

LoadPlanner acts as an access proxy to the state_dict, so any transformation done to it will be visible to the whole process.

A planner subclass can expect the following sequence of calls during load_state_dict:

Signals the start of loading a checkpoint.

Process the state_dict and produces a LoadPlan that will be sent for global planning.

Takes the LoadPlan from all ranks and make any global decision.

This is called once per non-tensor value in state_dict.

They are called in pair for each Tensor value in state_dict.

Users are recommended to extend DefaultLoadPlanner instead of this interface directly as most changes can be expressed by changes in a single method.

There are two usual patterns of extension:

Rewriting state_dict. This is the simplest way to extend the load process as it doesn’t requite understanding the intrincacies of how LoadPlan works. We need to keep a reference to the original state_dict as load happens in place so we need to be able to perform it in place

Modifying resolve_tensor and commit_tensor to handle load time transformation.

Call once the StorageReader finished loading data into tensor.

The provided tensor is the same one returned by the call to resolve_tensor. This method is only needed if this LoadPlanner needs to post process tensor prior to copying it back to the one in the state_dict.

The contents of tensor will follow its device synchronization model.

Compute the global load plan and return plans for each rank.

. N.B. This is called on the coordinator rank only

list[torch.distributed.checkpoint.planner.LoadPlan]

Create a LoadPlan based on state_dict and metadata provided by set_up_planner.

. N.B. This is called on every rank.

Accept the plan from coordinator and return final LoadPlan.

Load the item described by read_item``and ``value.

This method is expected to modify in-place the underlying state_dict.

The contents of value are defined by the SavePlanner used to produce the checkpoint being loaded.

Return the BytesIO to be used by the StorageReader to load read_item.

The BytesIO should alias with one on the underlying state_dict as StorageReader will replace its contents.

Return the tensor described by read_item to be used by the StorageReader to load read_item.

The tensor should alias with one on the underlying state_dict as StorageReader will replace its contents. If, for any reason, that’s not possible, the planner can use the commit_tensor method to copy the data back to the one in state_dict.

Initialize this instance to load data into state_dict.

. N.B. This is called on every rank.

Abstract class defining the protocol used by save_state_dict to plan the save process.

SavePlanners are stateful objects that can be used to customize the whole save process.

SavePlanner acts as an access proxy to the state_dict, so any transformation done to it will be visible to the whole process.

A planner subclass can expect the following sequence of calls during save_state_dict:

Signals the start of a checkpoint save.

Process the state_dict and produces a SavePlan that will be sent for global planning.

Takes the SavePlan from all ranks and make any global decision.

This gives each rank a chance to adjust to global planning decisions.

Lookups a value on the state_dict for the storage layer to write.

Users are recommended to extend DefaultSavePlanner instead of this interface directly as most changes can be expressed by changes in a single method.

There are 3 usual patterns of extension:

Rewriting state_dict. This is the simplest way to extend the save process as it doesn’t requite understanding the intrincacies of how SavePlan works:

Modifying local plan and lookup in tandem. This is useful when fine control of how data is persisted

Using the global planning step to make central decisions that can’t be made individually by each rank

Finally, some planners need to save additional metadata in the checkpoint, this is accomplished by having each rank contribute their data items in the local plan and the global planner aggregate them:

Compute the global checkpoint plan and return the local plan of each rank.

This is called on the coordinator rank only.

tuple[list[torch.distributed.checkpoint.planner.SavePlan], torch.distributed.checkpoint.metadata.Metadata]

Compute the save plan for the current rank.

This will be aggregated and passed to create_global_plan. Planner specific data can be passed through SavePlan::planner_data.

This is called on all ranks.

Merge the plan created by create_local_plan and the result of create_global_plan.

This is called on all ranks.

Transform and prepare write_item from state_dict for storage, ensuring idempotency and thread-safety.

Lookup the object associated with write_item in state_dict and apply any transformation (such as serialization) prior to the storage layer consuming it.

Called on each rank multiple times, at least once per WriteItem in the final SavePlan.

This method should be idempotent and thread-save. StorageWriter implementations are free to call it as frequently as they need.

Any transformation that allocates memory should be lazily done when his method is called in order to reduce peak memory required by checkpointing.

When returning tensors, they can be on any device or format, they can be views too. It’s the storage layer responsibility to figure out how to save them.

Union[Tensor, BytesIO]

Initialize this planner to save state_dict.

Implementations should save those values as they won’t be provided lated in the save process.

This is called on all ranks.

Dataclass which holds information about what needs to be written to storage.

Calculates the storage size of the underlying tensor, or None if this is not a tensor write.

Optional[int] storage size, in bytes of underlying tensor if any.

We provide a filesystem based storage layer:

return the checkpoint_id that will be used to load the checkpoint.

Basic implementation of StorageWriter using file IO.

This implementation makes the following assumptions and simplifications:

The checkpoint path is an empty or non-existing directory.

File creation is atomic

The checkpoint consist of one file per write request plus a global .metadata file with the serialized metadata if rank coordination is enabled. a rank local __{rank}.metadata file with the serialized metadata if rank coordination is NOT enabled.

Override of AsyncStager.stage

dict[str, Union[~StatefulT, Any]]

We also provide other storage layers, including ones to interact with HuggingFace safetensors:

.. autoclass:: torch.distributed.checkpoint.HuggingFaceStorageReader :members:

.. autoclass:: torch.distributed.checkpoint.HuggingFaceStorageWriter :members:

.. autoclass:: torch.distributed.checkpoint.QuantizedHuggingFaceStorageReader :members:

We provide default implementations of LoadPlanner and SavePlanner that can handle all of torch.distributed constructs such as FSDP, DDP, ShardedTensor and DistributedTensor.

Extension from the planner interface to make it easy to extend the default planner.

Extension from the planner interface to make it easy to extend the default planner.

DefaultLoadPlanner that adds multiple features on top of LoadPlanner.

In particular it adds the following:

flatten_state_dict: Handle state_dict with nested dicts flatten_sharded_tensors: For FSDP in 2D parallel mode allow_partial_load: If False, will raise a runtime error if a key is present in state_dict, but not in the checkpoint.

Extension from the planner interface to make it easy to extend the default planner.

Extension from the planner interface to make it easy to extend the default planner.

Due to legacy design decisions, the state dictionaries of FSDP and DDP may have different keys or fully qualified names (e.g., layer1.weight) even when the original unparallelized model is identical. Moreover, FSDP offers various types of model state dictionaries, such as full and sharded state dictionaries. Additionally, optimizer state dictionaries employ parameter IDs instead of fully qualified names to identify parameters, potentially causing issues when parallelisms are used (e.g., pipeline parallelism).

To tackle these challenges, we offer a collection of APIs for users to easily manage state_dicts. get_model_state_dict() returns a model state dictionary with keys consistent with those returned by the unparallelized model state dictionary. Similarly, get_optimizer_state_dict() provides the optimizer state dictionary with keys uniform across all parallelisms applied. To achieve this consistency, get_optimizer_state_dict() converts parameter IDs to fully qualified names identical to those found in the unparallelized model state dictionary.

Note that results returned by these APIs can be used directly with the torch.distributed.checkpoint.save() and torch.distributed.checkpoint.load() methods without requiring any additional conversions.

set_model_state_dict() and set_optimizer_state_dict() are provided to load the model and optimizer state_dict generated by by their respective getter APIs.

Note that set_optimizer_state_dict() can only be called before backward() or after step() is called on optimizers.

Note that this feature is experimental, and API signatures might change in the future.

Return the model state_dict and optimizers state_dict.

get_state_dict can process any module that is parallelized by PyTorch FSDP/fully_shard, DDP/replicate, tensor_parallel/parallelize_module, and any combination of these parallelisms. The main functions of get_state_dict are: 1.) returning a model and optimizer state_dict that can be resharded with a different number of trainers and/or different parallelisms. 2.) hiding the parallelism-specific state_dict APIs. Users don’t have to call these APIs. 3.) sanity checking the result state_dict.

The keys of the result state dictionary are the canonical FQNs (Fully Qualified Names). A canonical FQN refers to the FQN based on a parameter’s position in an nn.Module hierarchy. More specifically, a canonical FQN to a parameter is the FQN returned by module.named_parameters() or module.named_buffers() when the module is not distributed by any parallelisms. Since the optimizer internally uses parameter IDs to represent a parameter, there will be a conversion from the parameter IDs to the canonical FQNs when calling this API.

get_state_dict can also process a module that is not parallelized. In such a case, get_state_dict only performs one function – converting the optimizer parameter IDs to the canonical FQNs.

model (nn.Module) – the nn.Module to the model.

optimizers (Union[None, Optimizer, Iterable[Optimizer]]) – The optimizers that are used to optimize model.

submodules (deprecated) – Optional[set[nn.Module]]: only return the model parameters that belong to the submodules.

options (StateDictOptions) – the options to control how model state_dict and optimizer state_dict should be returned. See StateDictOptions for the details.

Tuple that contain model state_dict and optimizer state_dict.

Tuple[Dict[str, ValueType], OptimizerStateType]

Return the model state_dict of model.

See get_state_dict for the detail usage.

model (nn.Module) – the nn.Module to the model.

submodules (deprecated) – Optional[set[nn.Module]]: only return the model parameters that belong to the submodules.

options (StateDictOptions) – the options to control how model state_dict and optimizer state_dict should be returned. See StateDictOptions for the details.

The state_dict for model.

Return the combined state_dict for optimizers.

See get_state_dict for the detail usage.

model (nn.Module) – the nn.Module to the model.

optimizers (Union[None, Optimizer, Iterable[Optimizer]]) – The optimizers that are used to optimize model.

submodules (deprecated) – Optional[set[nn.Module]]: only return the model parameters that belong to the submodules.

options (StateDictOptions) – the options to control how model state_dict and optimizer state_dict should be returned. See StateDictOptions for the details.

The state_dict for optimizers.

Load the model state_dict and optimizers state_dict.

The counterpart of get_state_dict to set the state_dict to the model and optimizers. The given model_state_dict and optim_state_dict do not have to be returned by get_state_dict but must meet the following requirements: 1) all FQNs are canonical FQNs as defined in get_state_dict, 2) if a tensor is sharded, it must be either a ShardedTensor or DTensor, 3) optimizer state_dict cannot contain the parameter IDs; the keys should be the canonical FQNs.

is called on the optimizers. Otherwise, the optimizer states won’t be initialized correctly.

model (nn.Module) – the nn.Module to the model.

optimizers (Union[Optimizer, Iterable[Optimizer]]) – The optimizers that are used to optimize model.

model_state_dict (Dict[str, ValueType]) – (Union[Dict[nn.Module, Dict[str, ValueType]], Dict[str, ValueType]]): the model state_dict to load. If the key of the model_state_dict is nn.Module, the key is a submodule of model and the value should be the state_dict of the submodule. When loading the state_dict, the prefix of the submodule will be append to the state_dict.

optim_state_dict (OptimizerStateType) – OptimizerStateType: the optimizer state_dict to load.

options (StateDictOptions) – the options to control how model state_dict and optimizer state_dict should be loaded. See StateDictOptions for the details.

missing_keys is a list of str containing the missing keys of the model state_dict. unexpected_keys is a list of str containing the unexpected keys of the model state_dict.

missing_keys is a list of str containing the missing keys of the model state_dict.

unexpected_keys is a list of str containing the unexpected keys of the model state_dict.

NamedTuple with missing_keys and unexpected_keys fields

Load the model state_dict.

The counterpart of get_model_state_dict to set the state_dict to the model. See set_state_dict for the detail usage.

model (nn.Module) – the nn.Module to the model.

model_state_dict (Dict[str, ValueType]) – (Dict[str, ValueType]): the model state_dict to load. If the key of the model_state_dict is nn.Module, the key is a submodule of model and the value should be the state_dict of the submodule. When loading the state_dict, the prefix of the submodule will be append to the state_dict.

options (StateDictOptions) – the options to control how model state_dict and optimizer state_dict should be loaded. See StateDictOptions for the details.

missing_keys is a list of str containing the missing keys unexpected_keys is a list of str containing the unexpected keys

missing_keys is a list of str containing the missing keys

unexpected_keys is a list of str containing the unexpected keys

NamedTuple with missing_keys and unexpected_keys fields

Load the optimizers state_dict.

The counterpart of get_optimizer_state_dict to set the state_dict to the optimizers. See set_state_dict for the detail usage.

step() is called on the optimizers. Otherwise, the optimizer states won’t be initialized correctly.

model (nn.Module) – the nn.Module to the model.

optimizers (Union[Optimizer, Iterable[Optimizer]]) – The optimizers that are used to optimize model.

optim_state_dict (OptimizerStateType) – OptimizerStateType: the optimizer state_dict to load.

options (StateDictOptions) – the options to control how model state_dict and optimizer state_dict should be loaded. See StateDictOptions for the details.

This dataclass specifies how get_state_dict/set_state_dict will work.

full_state_dict: if this is set to True, all the tensors in the returned state_dict will be gathered. No ShardedTensor and DTensor will be in the returned state_dict.

cpu_offload: offload all the tensors to cpu. To prevent CPU OOM, if full_state_dict is also true, then only the rank0 will get the state_dict and all other ranks will get empty state_dict.

ignore_frozen_params: if the value is True, the returned state_dict won’t contain any frozen parameters – the requires_grad is False. The default value is False.

keep_submodule_prefixes (deprecated): when submodules is not None, this option indicates whether to keep the submodule prefixes from the state_dict keys. or example, if the submodule is module.pretrain and the full FQN of the parameter is pretrain.layer1.weight of the param. When this option is True, the parameter’s key in the returned state_dict will be pretrain.layer1.weight. If the options is False, the key will be layer1.weight. Note that if keep_submodule_prefixes is False, there may be conflicted FQNs, hence there should be only one submodule in submodules.

strict: the strict option when set_state_dict calls model.load_state_dict().

full state_dict and will broadcast the tensors in the state_dict/ optim_state_dict one by one to other ranks. Other ranks will receive the tensors and shard according to the local shards in the model and optimizer. full_state_dict must be set to True when using this option. This option currently only supports DTensor, not the legacy ShardedTensor.

For users which are used to using and sharing models in the torch.save format, the following methods are provided which provide offline utilities for converting betweeing formats.

Given a directory containing a DCP checkpoint, this function will convert it into a Torch save file.

dcp_checkpoint_dir (Union[str, PathLike]) – Directory containing the DCP checkpoint.

torch_save_path (Union[str, PathLike]) – Filename to store the converted Torch save file.

To avoid OOM, it’s recommended to only run this function on a single rank.

Given the location of a torch save file, converts it into a DCP checkpoint.

torch_save_path (Union[str, PathLike]) – Filename of the Torch save file.

dcp_checkpoint_dir (Union[str, PathLike]) – Directory to store the DCP checkpoint.

To avoid OOM, it’s recommended to only run this function on a single rank.

The following classes can also be utilized for online loading and resharding of models from the torch.save format.

StorageReader for reading a Torch Save file. This reader will read the entire checkpoint on the coordinator rank, and then broadcast and shard each tensor to all ranks.

. N.B. Intended to be used with DynamicMetaLoadPlanner

Current implementation only supports loading Tensors.

Implementation of the StorageReader method

list[torch.distributed.checkpoint.planner.LoadPlan]

Implementation of the StorageReader method

Reads torch save data on the coordinator rank, and broadcast afterwards this incurrs a communication cost, but avoids having to load the entire checkpoint on each rank, hopefully preventing OOM issues

Extends the default StorageReader to support building the metadata file

Implementation of the StorageReader method

Implementation of the StorageReader method

Implementation of the StorageReader method

Extension of DefaultLoadPlanner, which creates a new Metadata object based on the passed in state dict, avoiding the need to read metadata from disk. This is useful when reading formats which don’t have a metadata file, like Torch Save files.

. N.B. Intended to be used with BroadcastingTorchSaveReader

Current implementation only supports loading Tensors.

Setups of the planner, extnding default behavior by creating the Metadata object from the state dict

The following experimental interfaces are provided for improved observability in production environments:

---

## torch.distributed.tensor#

**URL:** https://pytorch.org/docs/stable/distributed.tensor.html

**Contents:**
- torch.distributed.tensor#
- PyTorch DTensor (Distributed Tensor)#
  - DTensor Class APIs#
  - DeviceMesh as the distributed communicator#
  - DTensor Placement Types#
- Different ways to create a DTensor#
  - Create DTensor from a logical torch.Tensor#
  - DTensor Factory Functions#
  - Random Operations#
- Debugging#

Created On: Jun 13, 2025 | Last Updated On: Aug 23, 2025

torch.distributed.tensor is currently in alpha state and under development, we are committing backward compatibility for the most APIs listed in the doc, but there might be API changes if necessary.

PyTorch DTensor offers simple and flexible tensor sharding primitives that transparently handles distributed logic, including sharded storage, operator computation and collective communications across devices/hosts. DTensor could be used to build different parallelism solutions and support sharded state_dict representation when working with multi-dimensional sharding.

Please see examples from the PyTorch native parallelism solutions that are built on top of DTensor:

DTensor follows the SPMD (single program, multiple data) programming model to empower users to write distributed program as if it’s a single-device program with the same convergence property. It provides a uniform tensor sharding layout (DTensor Layout) through specifying the DeviceMesh and Placement:

DeviceMesh represents the device topology and the communicators of the cluster using an n-dimensional array.

Placement describes the sharding layout of the logical tensor on the DeviceMesh. DTensor supports three types of placements: Shard, Replicate and Partial.

DTensor is a torch.Tensor subclass. This means once a DTensor is created, it could be used in very similar way to torch.Tensor, including running different types of PyTorch operators as if running them in a single device, allowing proper distributed computation for PyTorch operators.

In addition to existing torch.Tensor methods, it also offers a set of additional methods to interact with torch.Tensor, redistribute the DTensor Layout to a new DTensor, get the full tensor content on all devices, etc.

DTensor (Distributed Tensor) is a subclass of torch.Tensor that provides single-device like abstraction to program with multi-device torch.Tensor. It describes the distributed tensor sharding layout (DTensor Layout) through the DeviceMesh and following types of Placement:

Shard: Tensor sharded on the tensor dimension dim on the devices of the DeviceMesh dimension

Replicate: Tensor replicated on the devices of the DeviceMesh dimension

Partial: Tensor is pending reduction on the devices of the DeviceMesh dimension

When calling PyTorch operators, DTensor overrides the PyTorch operators to perform sharded computation and issue communications whenever necessary. Along with the operator computation, DTensor will transform or propagate the placements (DTensor Layout) properly (based on the operator semantic itself) and generate new DTensor outputs.

To ensure numerical correctness of the DTensor sharded computation when calling PyTorch operators, DTensor requires every Tensor argument of the operator be DTensor.

Directly using the Tensor subclass constructor here is not the recommended way to create a DTensor (i.e. it does not handle autograd correctly hence is not the public API). Please refer to the create_dtensor section to see how to create a DTensor.

Return a list of ChunkStorageMetadata, which is a dataclass that describes the size/offset of the local shard/replica on current rank. For DTensor, each rank will have a single local shard/replica, so the returned list usually only has one element.

This dunder method is primariy used for distributed checkpoint purpose.

A List[ChunkStorageMetadata] object that represents the shard size/offset on the current rank.

Create a DTensor from a local torch.Tensor on each rank according to the device_mesh and placements specified.

local_tensor (torch.Tensor) – local torch.Tensor on each rank.

device_mesh (DeviceMesh, optional) – DeviceMesh to place the tensor, if not specified, must be called under a DeviceMesh context manager, default: None

placements (List[Placement], optional) – the placements that describes how to place the local torch.Tensor on DeviceMesh, must have the same number of elements as device_mesh.ndim.

run_check (bool, optional) – at a cost of extra communications, perform sanity check across ranks to check each local tensor’s meta information to ensure correctness. If have Replicate in placements, the data on first rank of the device mesh dimension will be broadcasted to other ranks. default: False

shape (torch.Size, optional) – A List of int which specifies the size of DTensor which build on top of local_tensor. Note this needs to be provided if the shape of local_tensor are different across the ranks. If not provided, shape will be computed assuming the given distributed tensor is evenly sharded across ranks. default: None

stride (tuple, optional) – A List of int which specifies the stride of DTensor. If not provided, stride will be computed assuming the given distributed tensor is evenly sharded across ranks. default: None

When run_check=False, it is the user’s responsibility to ensure the local tensor passed in is correct across ranks (i.e. the tensor is sharded for the Shard(dim) placement or replicated for the Replicate() placement). If not, the behavior of the created DTensor is undefined.

from_local is differentiable, the requires_grad of the created DTensor object will depend on if local_tensor requires_grad or not.

Return the full tensor of this DTensor. It will perform necessary collectives to gather the local tensors from other ranks in its DeviceMesh and concatenate them together. It’s a syntactic sugar of the following code:

dtensor.redistribute(placements=[Replicate()] * mesh.ndim).to_local()

grad_placements (List[Placement], optional) – the placements describes the future layout of any gradient layout of the full Tensor returned from this function. full_tensor converts DTensor to a full torch.Tensor and the returned torch.tensor might not be used as the original replicated DTensor layout later in the code. This argument is the hint that user can give to autograd in case the gradient layout of the returned tensor does not match the original replicated DTensor layout. If not specified, we will assume the gradient layout of the full tensor be replicated.

A torch.Tensor object that represents the full tensor of this DTensor.

full_tensor is differentiable.

redistribute performs necessary collective operations that redistribute the current DTensor from its current placements to a new placements, or from its current DeviceMesh to a new DeviceMesh. i.e. we can turn a Sharded DTensor to a Replicated DTensor by specifying a Replicate placement for each dimension of the DeviceMesh.

When redistributing from current to the new placements on one device mesh dimension, we will perform the following operations including communication collective or local operation:

Shard(dim) -> Replicate(): all_gather

Shard(src_dim) -> Shard(dst_dim): all_to_all

Replicate() -> Shard(dim): local chunking (i.e. torch.chunk)

Partial() -> Replicate(): all_reduce

Partial() -> Shard(dim): reduce_scatter

redistribute would correctly figure out the necessary redistribute steps for DTensors that are created either on 1-D or N-D DeviceMesh.

device_mesh (DeviceMesh, optional) – DeviceMesh to place the DTensor. If not specified, it would use the current DTensor’s DeviceMesh. default: None

placements (List[Placement], optional) – the new placements that describes how to place the DTensor into the DeviceMesh, must have the same number of elements as device_mesh.ndim. default: replicate on all mesh dimensions

async_op (bool, optional) – whether to perform the DTensor redistribute operation asynchronously or not. Default: False

forward_dtype (torch.dtype, optional) – the local tensor datatype can be converted to forward_dtype before redistributing the local tensor in its forward. The result DTensor will be in forward_dtype Default: None.

backward_dtype (torch.dtype, optional) – the local tensor datatype can be converted to backward_dtype before redistributing the local tensor in its backward. The result DTensor gradient would be converted back to the current DTensor dtype. Default: None

redistribute is differentiable, which means user do not need to worry about the backward formula of the redistribute operation.

redistribute currently only supports redistributing DTensor on the same DeviceMesh, Please file an issue if you need to redistribute DTensor to different DeviceMesh.

Get the local tensor of this DTensor on its current rank. For sharding it returns a local shard of the logical tensor view, for replication it returns the replica on its current rank.

grad_placements (List[Placement], optional) – the placements describes the future layout of any gradient layout of the Tensor returned from this function. to_local converts DTensor to local tensor and the returned local tensor might not be used as the original DTensor layout later in the code. This argument is the hint that user can give to autograd in case the gradient layout of the returned tensor does not match the original DTensor layout. If not specified, we will assume the gradient layout remains the same as the original DTensor and use that for gradient computation.

A torch.Tensor or AsyncCollectiveTensor object. it represents the local tensor on its current rank. When an AsyncCollectiveTensor object is returned, it means the local tensor is not ready yet (i.e. communication is not finished). In this case, user needs to call wait to wait the local tensor to be ready.

to_local is differentiable, the requires_grad of the local tensor returned will depend on if the DTensor requires_grad or not.

The DeviceMesh attribute that associates with this DTensor object.

device_mesh is a read-only property, it can not be set.

The placements attribute of this DTensor that describes the layout of this DTensor on the its DeviceMesh.

placements is a read-only property, it can not be set.

DeviceMesh was built from DTensor as the abstraction to describe cluster’s device topology and represent multi-dimensional communicators (on top of ProcessGroup). To see the details of how to create/use a DeviceMesh, please refer to the DeviceMesh recipe.

DTensor supports the following types of Placement on each DeviceMesh dimension:

The Shard(dim) placement describes the DTensor sharding on tensor dimension dim over a corresponding DeviceMesh dimension, where each rank on the DeviceMesh dimension only holds a shard/piece of the global Tensor. The Shard(dim) placement follows the torch.chunk(dim) semantic, where the last few shards on the DeviceMesh dimension might be empty when the tensor dimension is not evenly divisible on the DeviceMesh dimension. The Shard placement can be used by all DTensor APIs (i.e. distribute_tensor, from_local, etc.)

dim (int) – The tensor dimension that describes the DTensor is sharded over its corresponding DeviceMesh dimension.

sharding on a tensor dimension where the tensor dimension size is not evenly divisible on a DeviceMesh dimension is currently experimental and subject to change.

The Replicate() placement describes the DTensor replicating on a corresponding DeviceMesh dimension, where each rank on the DeviceMesh dimension holds a replica of the global Tensor. The Replicate placement can be used by all DTensor APIs (i.e. distribute_tensor, DTensor.from_local, etc.)

The Partial(reduce_op) placement describes the DTensor that is pending reduction on a specified DeviceMesh dimension, where each rank on the DeviceMesh dimension holds the partial value of the global Tensor. User can redistribute the Partial DTensor to a Replicate or Shard(dim) placement on the specified DeviceMesh dimension using redistribute, which would trigger necessary communication operations under the hood (i.e. allreduce, reduce_scatter).

reduce_op (str, optional) – The reduction op to be used for the partial DTensor to produce Replicated/Sharded DTensor. Only element-wise reduction operations are supported, including: “sum”, “avg”, “product”, “max”, “min”, default: “sum”.

The Partial placement can be generated as a result of the DTensor operators, and can only be used by the DTensor.from_local API.

The base class for the Placement type, where it describes how a DTensor is placed onto the DeviceMesh. Placement and DeviceMesh together could describe the DTensor Layout. It is the base class of the three main DTensor Placement types: Shard, Replicate, and Partial.

This class is not meant to be used directly, mainly served as a typing stub.

distribute_tensor() creates a DTensor from a logical or “global” torch.Tensor on each rank. This could be used to shard the leaf torch.Tensor s (i.e. model parameters/buffers and inputs).

DTensor.from_local() creates a DTensor from a local torch.Tensor on each rank, which can be used to create DTensor from a non-leaf torch.Tensor s (i.e. intermediate activation tensors during forward/backward).

DTensor provides dedicated tensor factory functions (e.g. empty(), ones(), randn(), etc.) to allow different DTensor creations by directly specifying the DeviceMesh and Placement. Compare to distribute_tensor(), this could directly materializing the sharded memory on device, instead of performing sharding after initializing the logical Tensor memory.

The SPMD (single program, multiple data) programming model in torch.distributed launches multiple processes (i.e. via torchrun) to execute the same program, this means that the model inside the program would be initialized on different processes first (i.e. the model might be initialized on CPU, or meta device, or directly on GPU if enough memory).

DTensor offers a distribute_tensor() API that could shard the model weights or Tensors to DTensor s, where it would create a DTensor from the “logical” Tensor on each process. This would empower the created DTensor s to comply with the single device semantic, which is critical for numerical correctness.

Distribute a leaf torch.Tensor (i.e. nn.Parameter/buffers) to the device_mesh according to the placements specified. The rank of device_mesh and placements must be the same. The tensor to distribute is the logical or “global” tensor, and the API would use the tensor from first rank of the DeviceMesh dimension as the source of truth to preserve the single-device semantic. If you want to construct a DTensor in the middle of the Autograd computation, please use DTensor.from_local() instead.

tensor (torch.Tensor) – torch.Tensor to be distributed. Note that if you want to shard a tensor on a dimension that is not evenly divisible by the number of devices in that mesh dimension, we use torch.chunk semantic to shard the tensor and scatter the shards. The uneven sharding behavior is experimental and subject to change.

device_mesh (DeviceMesh, optional) – DeviceMesh to distribute the tensor, if not specified, must be called under a DeviceMesh context manager, default: None

placements (List[Placement], optional) – the placements that describes how to place the tensor on DeviceMesh, must have the same number of elements as device_mesh.ndim. If not specified, we will by default replicate the tensor across the device_mesh from the first rank of each dimension of the device_mesh.

src_data_rank (int, optional) – the rank of the source data for the logical/global tensor, it is used by distribute_tensor() to scatter/broadcast the shards/replicas to other ranks. By default, we use group_rank=0 on each DeviceMesh dimension as the source data to preserve the single-device semantic. If passing None explicitly, distribute_tensor() simply uses its local data instead of trying to preserve the single-device semantic via scatter/broadcast. Default: 0

A DTensor or XLAShardedTensor object.

When initialize the DeviceMesh with the xla device_type, distribute_tensor return XLAShardedTensor instead. see this issue for more details. The XLA integration is experimental and subject to change.

Along with distribute_tensor(), DTensor also offers a distribute_module() API to allow easier sharding on the nn.Module level

This function expose three functions to control the parameters/inputs/outputs of the module:

1. To perform sharding on the module before runtime execution by specifying the partition_fn (i.e. allow user to convert Module parameters to DTensor parameters according to the partition_fn specified). 2. To control the inputs or outputs of the module during runtime execution by specifying the input_fn and output_fn. (i.e. convert the input to DTensor, convert the output back to torch.Tensor)

module (nn.Module) – user module to be partitioned.

device_mesh (DeviceMesh) – the device mesh to place the module.

partition_fn (Callable) – the function to partition parameters (i.e. shard certain parameters across the device_mesh). If partition_fn is not specified, by default we replicate all module parameters of module across the mesh.

input_fn (Callable) – specify the input distribution, i.e. could control how the input of the module is sharded. input_fn will be installed as a module forward_pre_hook (pre forward hook).

output_fn (Callable) – specify the output distribution, i.e. could control how the output is sharded, or convert it back to torch.Tensor. output_fn will be installed as a module forward_hook (post forward hook).

A module that contains parameters/buffers that are all DTensor s.

When initialize the DeviceMesh with the xla device_type, distribute_module return nn.Module with PyTorch/XLA SPMD annotated parameters. See this issue for more details. The XLA integration is experimental and subject to change.

DTensor also provides dedicated tensor factory functions to allow creating DTensor directly using torch.Tensor like factory function APIs (i.e. torch.ones, torch.empty, etc), by additionally specifying the DeviceMesh and Placement for the DTensor created:

Returns a DTensor filled with the scalar value 0.

size (int...) – a sequence of integers defining the shape of the output DTensor. Can be a variable number of arguments or a collection like a list or tuple. E.g.: zeros(1,2,3..) or zeros([1,2,3..]) or zeros((1,2,3..))

requires_grad (bool, optional) – If autograd should record operations on the returned DTensor. Default: False.

dtype (torch.dtype, optional) – the desired data type of returned DTensor. Default: if None, uses a global default (see torch.set_default_dtype()).

layout (torch.layout, optional) – the desired layout of returned DTensor. Default: torch.strided.

device_mesh – DeviceMesh type, contains the mesh info of ranks

placements – a sequence of Placement type: Shard, Replicate

A DTensor object on each rank

Returns a DTensor filled with the scalar value 1, with the shape defined by the variable argument size.

size (int...) – a sequence of integers defining the shape of the output DTensor. Can be a variable number of arguments or a collection like a list or tuple. E.g.: ones(1,2,3..) or ones([1,2,3..]) or ones((1,2,3..))

dtype (torch.dtype, optional) – the desired data type of returned DTensor. Default: if None, uses a global default (see torch.set_default_dtype()).

layout (torch.layout, optional) – the desired layout of returned DTensor. Default: torch.strided.

requires_grad (bool, optional) – If autograd should record operations on the returned DTensor. Default: False.

device_mesh – DeviceMesh type, contains the mesh info of ranks

placements – a sequence of Placement type: Shard, Replicate

A DTensor object on each rank

Returns a DTensor filled with uninitialized data. The shape of the DTensor is defined by the variable argument size.

size (int...) – a sequence of integers defining the shape of the output DTensor. Can be a variable number of arguments or a collection like a list or tuple. E.g.: empty(1,2,3..) or empty([1,2,3..]) or empty((1,2,3..))

dtype (torch.dtype, optional) – the desired data type of returned DTensor. Default: if None, uses a global default (see torch.set_default_dtype()). layout (torch.layout, optional): the desired layout of returned DTensor. Default: torch.strided.

requires_grad (bool, optional) – If autograd should record operations on the returned DTensor. Default: False.

device_mesh – DeviceMesh type, contains the mesh info of ranks

placements – a sequence of Placement type: Shard, Replicate

A DTensor object on each rank

Returns a DTensor filled with fill_value according to device_mesh and placements, with the shape defined by the argument size.

size (int...) – a sequence of integers defining the shape of the output DTensor. Can be a variable number of arguments or a collection like a list or tuple. E.g.: ones(1,2,3..) or ones([1,2,3..]) or ones((1,2,3..))

fill_value (Scalar) – the value to fill the output tensor with.

dtype (torch.dtype, optional) – the desired data type of returned DTensor. Default: if None, uses a global default (see torch.set_default_dtype()).

layout (torch.layout, optional) – the desired layout of returned DTensor. Default: torch.strided.

requires_grad (bool, optional) – If autograd should record operations on the returned DTensor. Default: False.

device_mesh – DeviceMesh type, contains the mesh info of ranks.

placements – a sequence of Placement type: Shard, Replicate

A DTensor object on each rank

Returns a DTensor filled with random numbers from a uniform distribution on the interval [0, 1). The shape of the tensor is defined by the variable argument size.

size (int...) – a sequence of integers defining the shape of the output DTensor. Can be a variable number of arguments or a collection like a list or tuple. E.g.: ones(1,2,3..) or ones([1,2,3..]) or ones((1,2,3..))

dtype (torch.dtype, optional) – the desired data type of returned DTensor. Default: if None, uses a global default (see torch.set_default_dtype()).

layout (torch.layout, optional) – the desired layout of returned DTensor. Default: torch.strided.

requires_grad (bool, optional) – If autograd should record operations on the returned DTensor. Default: False.

device_mesh – DeviceMesh type, contains the mesh info of ranks.

placements – a sequence of Placement type: Shard, Replicate

A DTensor object on each rank

Returns a DTensor filled with random numbers from a normal distribution with mean 0 and variance 1. The shape of the tensor is defined by the variable argument size.

size (int...) – a sequence of integers defining the shape of the output DTensor. Can be a variable number of arguments or a collection like a list or tuple. E.g.: ones(1,2,3..) or ones([1,2,3..]) or ones((1,2,3..))

dtype (torch.dtype, optional) – the desired data type of returned DTensor. Default: if None, uses a global default (see torch.set_default_dtype()).

layout (torch.layout, optional) – the desired layout of returned DTensor. Default: torch.strided.

requires_grad (bool, optional) – If autograd should record operations on the returned DTensor. Default: False.

device_mesh – DeviceMesh type, contains the mesh info of ranks.

placements – a sequence of Placement type: Shard, Replicate

A DTensor object on each rank

DTensor provides distributed RNG functionality to ensure that random operations on sharded tensors get unique values, and random operations on replicated tensors get the same values. This system requires that all participating ranks (e.g. SPMD ranks) start out using the same generator state before each dtensor random operation is performed, and if this is true, it ensures they all end up at the same state after each dtensor random operation completes. There is no communication performed during random operations to synchronize RNG states.

Operators that accept a generator kwarg will utilize the user-passed generator, if passed, or the default generator for the device otherwise. Whichever generator is used, it will be advanced after the DTensor operation. It is valid to use the same generator for both DTensor and non-DTensor operations, but care must be taken to ensure the non-DTensor operations advance the generator state equally on all ranks if so.

When using DTensor together with Pipeline Parallelism, ranks for each pipeline stage should use a distinct seed, and ranks within a pipeline stage should use the same seed.

DTensor’s RNG infra is based on the philox based RNG algorithm, and supports any philox based backend (cuda, and other cuda-like devices), but unfortunately does not yet support the CPU backend.

When launching the program, you can turn on additional logging using the TORCH_LOGS environment variable from torch._logging :

TORCH_LOGS=+dtensor will display logging.DEBUG messages and all levels above it.

TORCH_LOGS=dtensor will display logging.INFO messages and above.

TORCH_LOGS=-dtensor will display logging.WARNING messages and above.

To debug the program that applied DTensor, and understand more details about what collectives happened under the hood, DTensor provides a CommDebugMode:

CommDebugMode is a context manager that counts the number of functional collectives within its context. It does this using a TorchDispatchMode.

Not all collectives are supported yet.

Generates detailed table displaying operations and collective tracing information on a module level. Amount of information is dependent on noise_level

prints module-level collective counts

prints dTensor operations not included in trivial operations, module information

prints operations not included in trivial operations

prints all operations

Creates json file used to build browser visual 0. prints module-level collective counts 1. prints dTensor operations not included in trivial operations 2. prints operations not included in trivial operations 3. prints all operations

Returns the communication counts as a dictionary.

The communication counts as a dictionary.

dict[str, dict[str, Any]]

dict[str, dict[str, Any]]

Alternative to console CommDebugMode output, writes to file specified by the user

To visualize the sharding of a DTensor that have less than 3 dimensions, DTensor provides visualize_sharding():

Visualizes sharding in the terminal for DTensor that are 1D or 2D.

This requires the tabulate package, or rich and matplotlib. No sharding info will be printed for empty tensors

DTensor also provides a set of experimental features. These features are either in prototyping stage, or the basic functionality is done and but looking for user feedbacks. Please submit a issue to PyTorch if you have feedbacks to these features.

context_parallel is an experimental API to enable context parallelism (CP). This API performs two actions: 1) patch the SDPA (torch.nn.functional.scaled_dot_product_attention) with the CP-enabled one, 2) shard buffers along the sequence dimension and each rank will preserve the corresponding shard according mesh.

mesh (DeviceMesh) – the device mesh for the context parallelism.

buffers (Optional[List[torch.Tensor]]) – buffers that the usage depend on the sequence dimension. Examples are input batch, labels and positional embedding buffers. These buffers must be sharded along the sequence dimension to ensure the accuracy. The sharding will happen in-place, the buffer’s shape will change within the context. The buffers will be restored after the context finishes. no_restore_buffers can be used to specify which buffers don’t need to be restored. Note that buffers should not contain any nn.Parameter.

buffer_seq_dims (Optional[List[int]]) – the sequence dimensions of buffers.

no_restore_buffers (Optional[Set[torch.Tensor]]) – buffers in these set won’t be restored after the context exits. This set must be a subset of buffers. If the buffers won’t be used after the context exits, these buffers can be put in this list to avoid extra restore time.

Generator[None, None, None]

torch.distributed.tensor.experimental.context_parallel is a prototype feature in PyTorch. The API is subject to change.

local_map() is an experimental API that allows users to pass DTensor s to a function that is written to be applied on torch.Tensor s. It is done by extracting the local components of DTensor, call the function, and wrap the outputs to DTensor according to the out_placements.

func (Callable) – the function to be applied on each local shard of DTensor s.

out_placements (Union[PlacementType, Tuple[PlacementType, …]]) – the desired placements of the DTensor s in func’s flattened output. If the flattened output is a single value, the out_placements should be of type PlacementType. Otherwise if the flattened output has multiple values, the out_placements should be a tuple of PlacementType values 1:1 mapping to the flattened output. Besides, for Tensor output, we use PlacementType as its placements (a Tuple[Placement] value). For non-Tensor output, the PlacementType should be None. Note that the only exception is when no DTensor argument is passed in. In this case, even if out_placements is not None, the result function should ignore the desired placements because the function is not running with DTensor s.

in_placements (Tuple[PlacementType, …], optional) – the required placements of the DTensor s in the flattened inputs of func. If in_placements is specified, local_map() would examine whether the placements of each DTensor argument is the same as the required placements or not. If the placements are not the same and redistribute_inputs is False, an exception will be raised. Otherwise if redistribute_inputs is True, the argument will be first redistributed to the required sharding placements before passing its local tensor to func. The only exception is when required placements are not None and the argument is a torch.Tensor. In this case, the placements examination will be skipped and the argument will be directly passed to func. If in_placements is None, no placements examination will be performed. Default: None

in_grad_placements (Tuple[PlacementType, …], optional) – the placements hint of the DTensor s gradient corresponds to the flattened input DTensor. This argument is the hint that user can give to to_local() in case the gradient layout of the local tensor input does not match its DTensor input layout. If not specified, we will assume the gradient layout of the local tensor input remains the same as the original DTensor input and use that for gradient computation. Default: None.

device_mesh (DeviceMesh, optional) – the device mesh that the output DTensor s are placed on. If not specified, this will be inferred from the first input DTensor’s device mesh. Default: None.

redistribute_inputs (bool, optional) – the bool value indicating whether to reshard the input DTensor s when their placements are different from the required input placements. If this value is False and some DTensor input has a different placement, an exception will be raised. Default: False.

A Callable that applies func to each local shard of the input DTensor and returns a DTensor constructed from the return value of func.

AssertionError – For any non-DTensor output, we require its corresponding output placement in out_placements be None. An AssertionError will be raised if this is not the case.

ValueError – If redistribute_inputs=False but the input DTensor needs a redistribution according to in_placements.

This API is currently experimental and subject to change

register_sharding() is an experimental API that allows users to register sharding strategies for an operator when the tensor inputs and outputs are DTensor. It can be useful when: (1) there doesn’t exist a default sharding strategy for op, e.g. when op is a custom operator that is not supported by DTensor; (2) when users would like to overwrite default sharding strategies of existing operators.

op (Union[OpOverload, List[OpOverload]]) – An op or a list of ops to register the customized sharding function.

A function decorator which can be used to wrap a function that defines the sharding strategy for the operator specified in op. The defined sharding strategy will be registered to DTensor and will override the default sharding strategy if DTensor has already implemented the operator. The customized sharding function takes the same inputs as the original op (except that if an arg is a torch.Tensor, it will be replaced by a tensor-like object that DTensor uses internally). The function should return a sequence of 2-tuples, each specifying acceptable output placements and its corresponding input placements.

This API is currently experimental and subject to change

---

## FullyShardedDataParallel#

**URL:** https://pytorch.org/docs/stable/fsdp.html

**Contents:**
- FullyShardedDataParallel#

Created On: Feb 02, 2022 | Last Updated On: Jun 11, 2025

A wrapper for sharding module parameters across data parallel workers.

This is inspired by Xu et al. as well as the ZeRO Stage 3 from DeepSpeed. FullyShardedDataParallel is commonly shortened to FSDP.

Using FSDP involves wrapping your module and then initializing your optimizer after. This is required since FSDP changes the parameter variables.

When setting up FSDP, you need to consider the destination CUDA device. If the device has an ID (dev_id), you have three options:

Place the module on that device

Set the device using torch.cuda.set_device(dev_id)

Pass dev_id into the device_id constructor argument.

This ensures that the FSDP instance’s compute device is the destination device. For option 1 and 3, the FSDP initialization always occurs on GPU. For option 2, the FSDP initialization happens on module’s current device, which may be a CPU.

If you’re using the sync_module_states=True flag, you need to ensure that the module is on a GPU or use the device_id argument to specify a CUDA device that FSDP will move the module to in the FSDP constructor. This is necessary because sync_module_states=True requires GPU communication.

FSDP also takes care of moving input tensors to the forward method to the GPU compute device, so you don’t need to manually move them from CPU.

For use_orig_params=True, ShardingStrategy.SHARD_GRAD_OP exposes the unsharded parameters, not the sharded parameters after forward, unlike ShardingStrategy.FULL_SHARD. If you want to inspect the gradients, you can use the summon_full_params method with with_grads=True.

With limit_all_gathers=True, you may see a gap in the FSDP pre-forward where the CPU thread is not issuing any kernels. This is intentional and shows the rate limiter in effect. Synchronizing the CPU thread in that way prevents over-allocating memory for subsequent all-gathers, and it should not actually delay GPU kernel execution.

FSDP replaces managed modules’ parameters with torch.Tensor views during forward and backward computation for autograd-related reasons. If your module’s forward relies on saved references to the parameters instead of reacquiring the references each iteration, then it will not see FSDP’s newly created views, and autograd will not work correctly.

Finally, when using sharding_strategy=ShardingStrategy.HYBRID_SHARD with the sharding process group being intra-node and the replication process group being inter-node, setting NCCL_CROSS_NIC=1 can help improve the all-reduce times over the replication process group for some cluster setups.

There are several limitations to be aware of when using FSDP:

FSDP currently does not support gradient accumulation outside no_sync() when using CPU offloading. This is because FSDP uses the newly-reduced gradient instead of accumulating with any existing gradient, which can lead to incorrect results.

FSDP does not support running the forward pass of a submodule that is contained in an FSDP instance. This is because the submodule’s parameters will be sharded, but the submodule itself is not an FSDP instance, so its forward pass will not all-gather the full parameters appropriately.

FSDP does not work with double backwards due to the way it registers backward hooks.

FSDP has some constraints when freezing parameters. For use_orig_params=False, each FSDP instance must manage parameters that are all frozen or all non-frozen. For use_orig_params=True, FSDP supports mixing frozen and non-frozen parameters, but it’s recommended to avoid doing so to prevent higher than expected gradient memory usage.

As of PyTorch 1.12, FSDP offers limited support for shared parameters. If enhanced shared parameter support is needed for your use case, please post in this issue.

You should avoid modifying the parameters between forward and backward without using the summon_full_params context, as the modifications may not persist.

module (nn.Module) – This is the module to be wrapped with FSDP.

process_group (Optional[Union[ProcessGroup, Tuple[ProcessGroup, ProcessGroup]]]) – This is the process group over which the model is sharded and thus the one used for FSDP’s all-gather and reduce-scatter collective communications. If None, then FSDP uses the default process group. For hybrid sharding strategies such as ShardingStrategy.HYBRID_SHARD, users can pass in a tuple of process groups, representing the groups over which to shard and replicate, respectively. If None, then FSDP constructs process groups for the user to shard intra-node and replicate inter-node. (Default: None)

sharding_strategy (Optional[ShardingStrategy]) – This configures the sharding strategy, which may trade off memory saving and communication overhead. See ShardingStrategy for details. (Default: FULL_SHARD)

cpu_offload (Optional[CPUOffload]) – This configures CPU offloading. If this is set to None, then no CPU offloading happens. See CPUOffload for details. (Default: None)

auto_wrap_policy (Optional[Union[Callable[[nn.Module, bool, int], bool], ModuleWrapPolicy, CustomPolicy]]) – This specifies a policy to apply FSDP to submodules of module, which is needed for communication and computation overlap and thus affects performance. If None, then FSDP only applies to module, and users should manually apply FSDP to parent modules themselves (proceeding bottom-up). For convenience, this accepts ModuleWrapPolicy directly, which allows users to specify the module classes to wrap (e.g. the transformer block). Otherwise, this should be a callable that takes in three arguments module: nn.Module, recurse: bool, and nonwrapped_numel: int and should return a bool specifying whether the passed-in module should have FSDP applied if recurse=False or if the traversal should continue into the module’s subtree if recurse=True. Users may add additional arguments to the callable. The size_based_auto_wrap_policy in torch.distributed.fsdp.wrap.py gives an example callable that applies FSDP to a module if the parameters in its subtree exceed 100M numel. We recommend printing the model after applying FSDP and adjusting as needed. Example: >>> def custom_auto_wrap_policy( >>> module: nn.Module, >>> recurse: bool, >>> nonwrapped_numel: int, >>> # Additional custom arguments >>> min_num_params: int = int(1e8), >>> ) -> bool: >>> return nonwrapped_numel >= min_num_params >>> # Configure a custom `min_num_params` >>> my_auto_wrap_policy = functools.partial(custom_auto_wrap_policy, min_num_params=int(1e5))

This specifies a policy to apply FSDP to submodules of module, which is needed for communication and computation overlap and thus affects performance. If None, then FSDP only applies to module, and users should manually apply FSDP to parent modules themselves (proceeding bottom-up). For convenience, this accepts ModuleWrapPolicy directly, which allows users to specify the module classes to wrap (e.g. the transformer block). Otherwise, this should be a callable that takes in three arguments module: nn.Module, recurse: bool, and nonwrapped_numel: int and should return a bool specifying whether the passed-in module should have FSDP applied if recurse=False or if the traversal should continue into the module’s subtree if recurse=True. Users may add additional arguments to the callable. The size_based_auto_wrap_policy in torch.distributed.fsdp.wrap.py gives an example callable that applies FSDP to a module if the parameters in its subtree exceed 100M numel. We recommend printing the model after applying FSDP and adjusting as needed.

backward_prefetch (Optional[BackwardPrefetch]) – This configures explicit backward prefetching of all-gathers. If None, then FSDP does not backward prefetch, and there is no communication and computation overlap in the backward pass. See BackwardPrefetch for details. (Default: BACKWARD_PRE)

mixed_precision (Optional[MixedPrecision]) – This configures native mixed precision for FSDP. If this is set to None, then no mixed precision is used. Otherwise, parameter, buffer, and gradient reduction dtypes can be set. See MixedPrecision for details. (Default: None)

ignored_modules (Optional[Iterable[torch.nn.Module]]) – Modules whose own parameters and child modules’ parameters and buffers are ignored by this instance. None of the modules directly in ignored_modules should be FullyShardedDataParallel instances, and any child modules that are already-constructed FullyShardedDataParallel instances will not be ignored if they are nested under this instance. This argument may be used to avoid sharding specific parameters at module granularity when using an auto_wrap_policy or if parameters’ sharding is not managed by FSDP. (Default: None)

param_init_fn (Optional[Callable[[nn.Module], None]]) – A Callable[torch.nn.Module] -> None that specifies how modules that are currently on the meta device should be initialized onto an actual device. As of v1.12, FSDP detects modules with parameters or buffers on meta device via is_meta and either applies param_init_fn if specified or calls nn.Module.reset_parameters() otherwise. For both cases, the implementation should only initialize the parameters/buffers of the module, not those of its submodules. This is to avoid re-initialization. In addition, FSDP also supports deferred initialization via torchdistX’s (pytorch/torchdistX) deferred_init() API, where the deferred modules are initialized by calling param_init_fn if specified or torchdistX’s default materialize_module() otherwise. If param_init_fn is specified, then it is applied to all meta-device modules, meaning that it should probably case on the module type. FSDP calls the initialization function before parameter flattening and sharding. Example: >>> module = MyModule(device="meta") >>> def my_init_fn(module: nn.Module): >>> # E.g. initialize depending on the module type >>> ... >>> fsdp_model = FSDP(module, param_init_fn=my_init_fn, auto_wrap_policy=size_based_auto_wrap_policy) >>> print(next(fsdp_model.parameters()).device) # current CUDA device >>> # With torchdistX >>> module = deferred_init.deferred_init(MyModule, device="cuda") >>> # Will initialize via deferred_init.materialize_module(). >>> fsdp_model = FSDP(module, auto_wrap_policy=size_based_auto_wrap_policy)

A Callable[torch.nn.Module] -> None that specifies how modules that are currently on the meta device should be initialized onto an actual device. As of v1.12, FSDP detects modules with parameters or buffers on meta device via is_meta and either applies param_init_fn if specified or calls nn.Module.reset_parameters() otherwise. For both cases, the implementation should only initialize the parameters/buffers of the module, not those of its submodules. This is to avoid re-initialization. In addition, FSDP also supports deferred initialization via torchdistX’s (pytorch/torchdistX) deferred_init() API, where the deferred modules are initialized by calling param_init_fn if specified or torchdistX’s default materialize_module() otherwise. If param_init_fn is specified, then it is applied to all meta-device modules, meaning that it should probably case on the module type. FSDP calls the initialization function before parameter flattening and sharding.

device_id (Optional[Union[int, torch.device]]) – An int or torch.device giving the CUDA device on which FSDP initialization takes place, including the module initialization if needed and the parameter sharding. This should be specified to improve initialization speed if module is on CPU. If the default CUDA device was set (e.g. via torch.cuda.set_device), then the user may pass torch.cuda.current_device to this. (Default: None)

sync_module_states (bool) – If True, then each FSDP module will broadcast module parameters and buffers from rank 0 to ensure that they are replicated across ranks (adding communication overhead to this constructor). This can help load state_dict checkpoints via load_state_dict in a memory efficient way. See FullStateDictConfig for an example of this. (Default: False)

forward_prefetch (bool) – If True, then FSDP explicitly prefetches the next forward-pass all-gather before the current forward computation. This is only useful for CPU-bound workloads, in which case issuing the next all-gather earlier may improve overlap. This should only be used for static-graph models since the prefetching follows the first iteration’s execution order. (Default: False)

limit_all_gathers (bool) – If True, then FSDP explicitly synchronizes the CPU thread to ensure GPU memory usage from only two consecutive FSDP instances (the current instance running computation and the next instance whose all-gather is prefetched). If False, then FSDP allows the CPU thread to issue all-gathers without any extra synchronization. (Default: True) We often refer to this feature as the “rate limiter”. This flag should only be set to False for specific CPU-bound workloads with low memory pressure in which case the CPU thread can aggressively issue all kernels without concern for the GPU memory usage.

use_orig_params (bool) – Setting this to True has FSDP use module ‘s original parameters. FSDP exposes those original parameters to the user via nn.Module.named_parameters() instead of FSDP’s internal FlatParameter s. This means that the optimizer step runs on the original parameters, enabling per-original-parameter hyperparameters. FSDP preserves the original parameter variables and manipulates their data between unsharded and sharded forms, where they are always views into the underlying unsharded or sharded FlatParameter, respectively. With the current algorithm, the sharded form is always 1D, losing the original tensor structure. An original parameter may have all, some, or none of its data present for a given rank. In the none case, its data will be like a size-0 empty tensor. Users should not author programs relying on what data is present for a given original parameter in its sharded form. True is required to use torch.compile(). Setting this to False exposes FSDP’s internal FlatParameter s to the user via nn.Module.named_parameters(). (Default: False)

ignored_states (Optional[Iterable[torch.nn.Parameter]], Optional[Iterable[torch.nn.Module]]) – Ignored parameters or modules that will not be managed by this FSDP instance, meaning that the parameters are not sharded and their gradients are not reduced across ranks. This argument unifies with the existing ignored_modules argument, and we may deprecate ignored_modules soon. For backward compatibility, we keep both ignored_states and ignored_modules`, but FSDP only allows one of them to be specified as not None.

device_mesh (Optional[DeviceMesh]) – DeviceMesh can be used as an alternative to process_group. When device_mesh is passed, FSDP will use the underlying process groups for all-gather and reduce-scatter collective communications. Therefore, these two args need to be mutually exclusive. For hybrid sharding strategies such as ShardingStrategy.HYBRID_SHARD, users can pass in a 2D DeviceMesh instead of a tuple of process groups. For 2D FSDP + TP, users are required to pass in device_mesh instead of process_group. For more DeviceMesh info, please visit: https://pytorch.org/tutorials/recipes/distributed_device_mesh.html

Apply fn recursively to every submodule (as returned by .children()) as well as self.

Typical use includes initializing the parameters of a model (see also torch.nn.init).

Compared to torch.nn.Module.apply, this version additionally gathers the full parameters before applying fn. It should not be called from within another summon_full_params context.

fn (Module -> None) – function to be applied to each submodule

Check if this instance is a root FSDP module.

Clip the gradient norm of all parameters.

The norm is computed over all parameters’ gradients as viewed as a single vector, and the gradients are modified in-place.

max_norm (float or int) – max norm of the gradients

norm_type (float or int) – type of the used p-norm. Can be 'inf' for infinity norm.

Total norm of the parameters (viewed as a single vector).

If every FSDP instance uses NO_SHARD, meaning that no gradients are sharded across ranks, then you may directly use torch.nn.utils.clip_grad_norm_().

If at least some FSDP instance uses a sharded strategy (i.e. one other than NO_SHARD), then you should use this method instead of torch.nn.utils.clip_grad_norm_() since this method handles the fact that gradients are sharded across ranks.

The total norm returned will have the “largest” dtype across all parameters/gradients as defined by PyTorch’s type promotion semantics. For example, if all parameters/gradients use a low precision dtype, then the returned norm’s dtype will be that low precision dtype, but if there exists at least one parameter/ gradient using FP32, then the returned norm’s dtype will be FP32.

This needs to be called on all ranks since it uses collective communications.

Flatten a sharded optimizer state-dict.

The API is similar to shard_full_optim_state_dict(). The only difference is that the input sharded_optim_state_dict should be returned from sharded_optim_state_dict(). Therefore, there will be all-gather calls on each rank to gather ShardedTensor s.

sharded_optim_state_dict (Dict[str, Any]) – Optimizer state dict corresponding to the unflattened parameters and holding the sharded optimizer state.

model (torch.nn.Module) – Refer to shard_full_optim_state_dict().

optim (torch.optim.Optimizer) – Optimizer for model ‘s parameters.

Refer to shard_full_optim_state_dict().

Run the forward pass for the wrapped module, inserting FSDP-specific pre- and post-forward sharding logic.

Return all nested FSDP instances.

This possibly includes module itself and only includes FSDP root modules if root_only=True.

module (torch.nn.Module) – Root module, which may or may not be an FSDP module.

root_only (bool) – Whether to return only FSDP root modules. (Default: False)

FSDP modules that are nested in the input module.

List[FullyShardedDataParallel]

Return the full optimizer state-dict.

Consolidates the full optimizer state on rank 0 and returns it as a dict following the convention of torch.optim.Optimizer.state_dict(), i.e. with keys "state" and "param_groups". The flattened parameters in FSDP modules contained in model are mapped back to their unflattened parameters.

This needs to be called on all ranks since it uses collective communications. However, if rank0_only=True, then the state dict is only populated on rank 0, and all other ranks return an empty dict.

Unlike torch.optim.Optimizer.state_dict(), this method uses full parameter names as keys instead of parameter IDs.

Like in torch.optim.Optimizer.state_dict(), the tensors contained in the optimizer state dict are not cloned, so there may be aliasing surprises. For best practices, consider saving the returned optimizer state dict immediately, e.g. using torch.save().

model (torch.nn.Module) – Root module (which may or may not be a FullyShardedDataParallel instance) whose parameters were passed into the optimizer optim.

optim (torch.optim.Optimizer) – Optimizer for model ‘s parameters.

optim_input (Optional[Union[List[Dict[str, Any]], Iterable[torch.nn.Parameter]]]) – Input passed into the optimizer optim representing either a list of parameter groups or an iterable of parameters; if None, then this method assumes the input was model.parameters(). This argument is deprecated, and there is no need to pass it in anymore. (Default: None)

rank0_only (bool) – If True, saves the populated dict only on rank 0; if False, saves it on all ranks. (Default: True)

group (dist.ProcessGroup) – Model’s process group or None if using the default process group. (Default: None)

A dict containing the optimizer state for model ‘s original unflattened parameters and including keys “state” and “param_groups” following the convention of torch.optim.Optimizer.state_dict(). If rank0_only=True, then nonzero ranks return an empty dict.

Get the state_dict_type and the corresponding configurations for the FSDP modules rooted at module.

The target module does not have to be an FSDP module.

A StateDictSettings containing the state_dict_type and state_dict / optim_state_dict configs that are currently set.

AssertionError` if the StateDictSettings for different –

FSDP submodules differ. –

Return the wrapped module.

Return an iterator over module buffers, yielding both the name of the buffer and the buffer itself.

Intercepts buffer names and removes all occurrences of the FSDP-specific flattened buffer prefix when inside the summon_full_params() context manager.

Iterator[tuple[str, torch.Tensor]]

Return an iterator over module parameters, yielding both the name of the parameter and the parameter itself.

Intercepts parameter names and removes all occurrences of the FSDP-specific flattened parameter prefix when inside the summon_full_params() context manager.

Iterator[tuple[str, torch.nn.parameter.Parameter]]

Disable gradient synchronizations across FSDP instances.

Within this context, gradients will be accumulated in module variables, which will later be synchronized in the first forward-backward pass after exiting the context. This should only be used on the root FSDP instance and will recursively apply to all children FSDP instances.

This likely results in higher memory usage because FSDP will accumulate the full model gradients (instead of gradient shards) until the eventual sync.

When used with CPU offloading, the gradients will not be offloaded to CPU when inside the context manager. Instead, they will only be offloaded right after the eventual sync.

Transform the state-dict of an optimizer corresponding to a sharded model.

The given state-dict can be transformed to one of three types: 1) full optimizer state_dict, 2) sharded optimizer state_dict, 3) local optimizer state_dict.

For full optimizer state_dict, all states are unflattened and not sharded. Rank0 only and CPU only can be specified via state_dict_type() to avoid OOM.

For sharded optimizer state_dict, all states are unflattened but sharded. CPU only can be specified via state_dict_type() to further save memory.

For local state_dict, no transformation will be performed. But a state will be converted from nn.Tensor to ShardedTensor to represent its sharding nature (this is not supported yet).

model (torch.nn.Module) – Root module (which may or may not be a FullyShardedDataParallel instance) whose parameters were passed into the optimizer optim.

optim (torch.optim.Optimizer) – Optimizer for model ‘s parameters.

optim_state_dict (Dict[str, Any]) – the target optimizer state_dict to transform. If the value is None, optim.state_dict() will be used. ( Default: None)

group (dist.ProcessGroup) – Model’s process group across which parameters are sharded or None if using the default process group. ( Default: None)

A dict containing the optimizer state for model. The sharding of the optimizer state is based on state_dict_type.

Convert an optimizer state-dict so that it can be loaded into the optimizer associated with the FSDP model.

Given a optim_state_dict that is transformed through optim_state_dict(), it gets converted to the flattened optimizer state_dict that can be loaded to optim which is the optimizer for model. model must be sharded by FullyShardedDataParallel.

model (torch.nn.Module) – Root module (which may or may not be a FullyShardedDataParallel instance) whose parameters were passed into the optimizer optim.

optim (torch.optim.Optimizer) – Optimizer for model ‘s parameters.

optim_state_dict (Dict[str, Any]) – The optimizer states to be loaded.

is_named_optimizer (bool) – Is this optimizer a NamedOptimizer or KeyedOptimizer. Only set to True if optim is TorchRec’s KeyedOptimizer or torch.distributed’s NamedOptimizer.

load_directly (bool) – If this is set to True, this API will also call optim.load_state_dict(result) before returning the result. Otherwise, users are responsible to call optim.load_state_dict() (Default: False)

group (dist.ProcessGroup) – Model’s process group across which parameters are sharded or None if using the default process group. ( Default: None)

Register a communication hook.

This is an enhancement that provides a flexible hook to users where they can specify how FSDP aggregates gradients across multiple workers. This hook can be used to implement several algorithms like GossipGrad and gradient compression which involve different communication strategies for parameter syncs while training with FullyShardedDataParallel.

FSDP communication hook should be registered before running an initial forward pass and only once.

state (object) – Passed to the hook to maintain any state information during the training process. Examples include error feedback in gradient compression, peers to communicate with next in GossipGrad, etc. It is locally stored by each worker and shared by all the gradient tensors on the worker.

Passed to the hook to maintain any state information during the training process. Examples include error feedback in gradient compression, peers to communicate with next in GossipGrad, etc. It is locally stored by each worker and shared by all the gradient tensors on the worker.

hook (Callable) – Callable, which has one of the following signatures: 1) hook: Callable[torch.Tensor] -> None: This function takes in a Python tensor, which represents the full, flattened, unsharded gradient with respect to all variables corresponding to the model this FSDP unit is wrapping (that are not wrapped by other FSDP sub-units). It then performs all necessary processing and returns None; 2) hook: Callable[torch.Tensor, torch.Tensor] -> None: This function takes in two Python tensors, the first one represents the full, flattened, unsharded gradient with respect to all variables corresponding to the model this FSDP unit is wrapping (that are not wrapped by other FSDP sub-units). The latter represents a pre-sized tensor to store a chunk of a sharded gradient after reduction. In both cases, callable performs all necessary processing and returns None. Callables with signature 1 are expected to handle gradient communication for a NO_SHARD case. Callables with signature 2 are expected to handle gradient communication for sharded cases.

Re-keys the optimizer state dict optim_state_dict to use the key type optim_state_key_type.

This can be used to achieve compatibility between optimizer state dicts from models with FSDP instances and ones without.

To re-key an FSDP full optimizer state dict (i.e. from full_optim_state_dict()) to use parameter IDs and be loadable to a non-wrapped model:

To re-key a normal optimizer state dict from a non-wrapped model to be loadable to a wrapped model:

The optimizer state dict re-keyed using the parameter keys specified by optim_state_key_type.

Scatter the full optimizer state dict from rank 0 to all other ranks.

Returns the sharded optimizer state dict on each rank. The return value is the same as shard_full_optim_state_dict(), and on rank 0, the first argument should be the return value of full_optim_state_dict().

Both shard_full_optim_state_dict() and scatter_full_optim_state_dict() may be used to get the sharded optimizer state dict to load. Assuming that the full optimizer state dict resides in CPU memory, the former requires each rank to have the full dict in CPU memory, where each rank individually shards the dict without any communication, while the latter requires only rank 0 to have the full dict in CPU memory, where rank 0 moves each shard to GPU memory (for NCCL) and communicates it to ranks appropriately. Hence, the former has higher aggregate CPU memory cost, while the latter has higher communication cost.

full_optim_state_dict (Optional[Dict[str, Any]]) – Optimizer state dict corresponding to the unflattened parameters and holding the full non-sharded optimizer state if on rank 0; the argument is ignored on nonzero ranks.

model (torch.nn.Module) – Root module (which may or may not be a FullyShardedDataParallel instance) whose parameters correspond to the optimizer state in full_optim_state_dict.

optim_input (Optional[Union[List[Dict[str, Any]], Iterable[torch.nn.Parameter]]]) – Input passed into the optimizer representing either a list of parameter groups or an iterable of parameters; if None, then this method assumes the input was model.parameters(). This argument is deprecated, and there is no need to pass it in anymore. (Default: None)

optim (Optional[torch.optim.Optimizer]) – Optimizer that will load the state dict returned by this method. This is the preferred argument to use over optim_input. (Default: None)

group (dist.ProcessGroup) – Model’s process group or None if using the default process group. (Default: None)

The full optimizer state dict now remapped to flattened parameters instead of unflattened parameters and restricted to only include this rank’s part of the optimizer state.

Set the state_dict_type of all the descendant FSDP modules of the target module.

Also takes (optional) configuration for the model’s and optimizer’s state dict. The target module does not have to be a FSDP module. If the target module is a FSDP module, its state_dict_type will also be changed.

This API should be called for only the top-level (root) module.

This API enables users to transparently use the conventional state_dict API to take model checkpoints in cases where the root FSDP module is wrapped by another nn.Module. For example, the following will ensure state_dict is called on all non-FSDP instances, while dispatching into sharded_state_dict implementation for FSDP:

module (torch.nn.Module) – Root module.

state_dict_type (StateDictType) – the desired state_dict_type to set.

state_dict_config (Optional[StateDictConfig]) – the configuration for the target state_dict_type.

optim_state_dict_config (Optional[OptimStateDictConfig]) – the configuration for the optimizer state dict.

A StateDictSettings that include the previous state_dict type and configuration for the module.

Shard a full optimizer state-dict.

Remaps the state in full_optim_state_dict to flattened parameters instead of unflattened parameters and restricts to only this rank’s part of the optimizer state. The first argument should be the return value of full_optim_state_dict().

Both shard_full_optim_state_dict() and scatter_full_optim_state_dict() may be used to get the sharded optimizer state dict to load. Assuming that the full optimizer state dict resides in CPU memory, the former requires each rank to have the full dict in CPU memory, where each rank individually shards the dict without any communication, while the latter requires only rank 0 to have the full dict in CPU memory, where rank 0 moves each shard to GPU memory (for NCCL) and communicates it to ranks appropriately. Hence, the former has higher aggregate CPU memory cost, while the latter has higher communication cost.

full_optim_state_dict (Dict[str, Any]) – Optimizer state dict corresponding to the unflattened parameters and holding the full non-sharded optimizer state.

model (torch.nn.Module) – Root module (which may or may not be a FullyShardedDataParallel instance) whose parameters correspond to the optimizer state in full_optim_state_dict.

optim_input (Optional[Union[List[Dict[str, Any]], Iterable[torch.nn.Parameter]]]) – Input passed into the optimizer representing either a list of parameter groups or an iterable of parameters; if None, then this method assumes the input was model.parameters(). This argument is deprecated, and there is no need to pass it in anymore. (Default: None)

optim (Optional[torch.optim.Optimizer]) – Optimizer that will load the state dict returned by this method. This is the preferred argument to use over optim_input. (Default: None)

The full optimizer state dict now remapped to flattened parameters instead of unflattened parameters and restricted to only include this rank’s part of the optimizer state.

Return the optimizer state-dict in its sharded form.

The API is similar to full_optim_state_dict() but this API chunks all non-zero-dimension states to ShardedTensor to save memory. This API should only be used when the model state_dict is derived with the context manager with state_dict_type(SHARDED_STATE_DICT):.

For the detailed usage, refer to full_optim_state_dict().

The returned state dict contains ShardedTensor and cannot be directly used by the regular optim.load_state_dict.

Set the state_dict_type of all the descendant FSDP modules of the target module.

This context manager has the same functions as set_state_dict_type(). Read the document of set_state_dict_type() for the detail.

module (torch.nn.Module) – Root module.

state_dict_type (StateDictType) – the desired state_dict_type to set.

state_dict_config (Optional[StateDictConfig]) – the model state_dict configuration for the target state_dict_type.

optim_state_dict_config (Optional[OptimStateDictConfig]) – the optimizer state_dict configuration for the target state_dict_type.

Expose full params for FSDP instances with this context manager.

Can be useful after forward/backward for a model to get the params for additional processing or checking. It can take a non-FSDP module and will summon full params for all contained FSDP modules as well as their children, depending on the recurse argument.

This can be used on inner FSDPs.

This can not be used within a forward or backward pass. Nor can forward and backward be started from within this context.

Parameters will revert to their local shards after the context manager exits, storage behavior is the same as forward.

The full parameters can be modified, but only the portion corresponding to the local param shard will persist after the context manager exits (unless writeback=False, in which case changes will be discarded). In the case where FSDP does not shard the parameters, currently only when world_size == 1, or NO_SHARD config, the modification is persisted regardless of writeback.

This method works on modules which are not FSDP themselves but may contain multiple independent FSDP units. In that case, the given arguments will apply to all contained FSDP units.

Note that rank0_only=True in conjunction with writeback=True is not currently supported and will raise an error. This is because model parameter shapes would be different across ranks within the context, and writing to them can lead to inconsistency across ranks when the context is exited.

Note that offload_to_cpu and rank0_only=False will result in full parameters being redundantly copied to CPU memory for GPUs that reside on the same machine, which may incur the risk of CPU OOM. It is recommended to use offload_to_cpu with rank0_only=True.

recurse (bool, Optional) – recursively summon all params for nested FSDP instances (default: True).

writeback (bool, Optional) – if False, modifications to params are discarded after the context manager exits; disabling this can be slightly more efficient (default: True)

rank0_only (bool, Optional) – if True, full parameters are materialized on only global rank 0. This means that within the context, only rank 0 will have full parameters and the other ranks will have sharded parameters. Note that setting rank0_only=True with writeback=True is not supported, as model parameter shapes will be different across ranks within the context, and writing to them can lead to inconsistency across ranks when the context is exited.

offload_to_cpu (bool, Optional) – If True, full parameters are offloaded to CPU. Note that this offloading currently only occurs if the parameter is sharded (which is only not the case for world_size = 1 or NO_SHARD config). It is recommended to use offload_to_cpu with rank0_only=True to avoid redundant copies of model parameters being offloaded to the same CPU memory.

with_grads (bool, Optional) – If True, gradients are also unsharded with the parameters. Currently, this is only supported when passing use_orig_params=True to the FSDP constructor and offload_to_cpu=False to this method. (Default: False)

This configures explicit backward prefetching, which improves throughput by enabling communication and computation overlap in the backward pass at the cost of slightly increased memory usage.

BACKWARD_PRE: This enables the most overlap but increases memory usage the most. This prefetches the next set of parameters before the current set of parameters’ gradient computation. This overlaps the next all-gather and the current gradient computation, and at the peak, it holds the current set of parameters, next set of parameters, and current set of gradients in memory.

BACKWARD_POST: This enables less overlap but requires less memory usage. This prefetches the next set of parameters after the current set of parameters’ gradient computation. This overlaps the current reduce-scatter and the next gradient computation, and it frees the current set of parameters before allocating memory for the next set of parameters, only holding the next set of parameters and current set of gradients in memory at the peak.

FSDP’s backward_prefetch argument accepts None, which disables the backward prefetching altogether. This has no overlap and does not increase memory usage. In general, we do not recommend this setting since it may degrade throughput significantly.

For more technical context: For a single process group using NCCL backend, any collectives, even if issued from different streams, contend for the same per-device NCCL stream, which implies that the relative order in which the collectives are issued matters for overlapping. The two backward prefetching values correspond to different issue orders.

This specifies the sharding strategy to be used for distributed training by FullyShardedDataParallel.

FULL_SHARD: Parameters, gradients, and optimizer states are sharded. For the parameters, this strategy unshards (via all-gather) before the forward, reshards after the forward, unshards before the backward computation, and reshards after the backward computation. For gradients, it synchronizes and shards them (via reduce-scatter) after the backward computation. The sharded optimizer states are updated locally per rank.

SHARD_GRAD_OP: Gradients and optimizer states are sharded during computation, and additionally, parameters are sharded outside computation. For the parameters, this strategy unshards before the forward, does not reshard them after the forward, and only reshards them after the backward computation. The sharded optimizer states are updated locally per rank. Inside no_sync(), the parameters are not resharded after the backward computation.

NO_SHARD: Parameters, gradients, and optimizer states are not sharded but instead replicated across ranks similar to PyTorch’s DistributedDataParallel API. For gradients, this strategy synchronizes them (via all-reduce) after the backward computation. The unsharded optimizer states are updated locally per rank.

HYBRID_SHARD: Apply FULL_SHARD within a node, and replicate parameters across nodes. This results in reduced communication volume as expensive all-gathers and reduce-scatters are only done within a node, which can be more performant for medium -sized models.

_HYBRID_SHARD_ZERO2: Apply SHARD_GRAD_OP within a node, and replicate parameters across nodes. This is like HYBRID_SHARD, except this may provide even higher throughput since the unsharded parameters are not freed after the forward pass, saving the all-gathers in the pre-backward.

This configures FSDP-native mixed precision training.

param_dtype (Optional[torch.dtype]) – This specifies the dtype for model parameters during forward and backward and thus the dtype for forward and backward computation. Outside forward and backward, the sharded parameters are kept in full precision (e.g. for the optimizer step), and for model checkpointing, the parameters are always saved in full precision. (Default: None)

reduce_dtype (Optional[torch.dtype]) – This specifies the dtype for gradient reduction (i.e. reduce-scatter or all-reduce). If this is None but param_dtype is not None, then this takes on the param_dtype value, still running gradient reduction in low precision. This is permitted to differ from param_dtype, e.g. to force gradient reduction to run in full precision. (Default: None)

buffer_dtype (Optional[torch.dtype]) – This specifies the dtype for buffers. FSDP does not shard buffers. Rather, FSDP casts them to buffer_dtype in the first forward pass and keeps them in that dtype thereafter. For model checkpointing, the buffers are saved in full precision except for LOCAL_STATE_DICT. (Default: None)

keep_low_precision_grads (bool) – If False, then FSDP upcasts gradients to full precision after the backward pass in preparation for the optimizer step. If True, then FSDP keeps the gradients in the dtype used for gradient reduction, which can save memory if using a custom optimizer that supports running in low precision. (Default: False)

cast_forward_inputs (bool) – If True, then this FSDP module casts its forward args and kwargs to param_dtype. This is to ensure that parameter and input dtypes match for forward computation, as required by many ops. This may need to be set to True when only applying mixed precision to some but not all FSDP modules, in which case a mixed-precision FSDP submodule needs to recast its inputs. (Default: False)

cast_root_forward_inputs (bool) – If True, then the root FSDP module casts its forward args and kwargs to param_dtype, overriding the value of cast_forward_inputs. For non-root FSDP modules, this does not do anything. (Default: True)

_module_classes_to_ignore (collections.abc.Sequence[type[torch.nn.modules.module.Module]]) – (Sequence[Type[nn.Module]]): This specifies module classes to ignore for mixed precision when using an auto_wrap_policy: Modules of these classes will have FSDP applied to them separately with mixed precision disabled (meaning that the final FSDP construction would deviate from the specified policy). If auto_wrap_policy is not specified, then this does not do anything. This API is experimental and subject to change. (Default: (_BatchNorm,))

This API is experimental and subject to change.

Only floating point tensors are cast to their specified dtypes.

In summon_full_params, parameters are forced to full precision, but buffers are not.

Layer norm and batch norm accumulate in float32 even when their inputs are in a low precision like float16 or bfloat16. Disabling FSDP’s mixed precision for those norm modules only means that the affine parameters are kept in float32. However, this incurs separate all-gathers and reduce-scatters for those norm modules, which may be inefficient, so if the workload permits, the user should prefer to still apply mixed precision to those modules.

By default, if the user passes a model with any _BatchNorm modules and specifies an auto_wrap_policy, then the batch norm modules will have FSDP applied to them separately with mixed precision disabled. See the _module_classes_to_ignore argument.

MixedPrecision has cast_root_forward_inputs=True and cast_forward_inputs=False by default. For the root FSDP instance, its cast_root_forward_inputs takes precedence over its cast_forward_inputs. For non-root FSDP instances, their cast_root_forward_inputs values are ignored. The default setting is sufficient for the typical case where each FSDP instance has the same MixedPrecision configuration and only needs to cast inputs to the param_dtype at the beginning of the model’s forward pass.

For nested FSDP instances with different MixedPrecision configurations, we recommend setting individual cast_forward_inputs values to configure casting inputs or not before each instance’s forward. In such a case, since the casts happen before each FSDP instance’s forward, a parent FSDP instance should have its non-FSDP submodules run before its FSDP submodules to avoid the activation dtype being changed due to a different MixedPrecision configuration.

The above shows a working example. On the other hand, if model[1] were replaced with model[0], meaning that the submodule using different MixedPrecision ran its forward first, then model[1] would incorrectly see float16 activations instead of bfloat16 ones.

This configures CPU offloading.

offload_params (bool) – This specifies whether to offload parameters to CPU when not involved in computation. If True, then this offloads gradients to CPU as well, meaning that the optimizer step runs on CPU.

StateDictConfig is the base class for all state_dict configuration classes. Users should instantiate a child class (e.g. FullStateDictConfig) in order to configure settings for the corresponding state_dict type supported by FSDP.

offload_to_cpu (bool) – If True, then FSDP offloads the state dict values to CPU, and if False, then FSDP keeps them on GPU. (Default: False)

FullStateDictConfig is a config class meant to be used with StateDictType.FULL_STATE_DICT. We recommend enabling both offload_to_cpu=True and rank0_only=True when saving full state dicts to save GPU memory and CPU memory, respectively. This config class is meant to be used via the state_dict_type() context manager as follows:

rank0_only (bool) – If True, then only rank 0 saves the full state dict, and nonzero ranks save an empty dict. If False, then all ranks save the full state dict. (Default: False)

ShardedStateDictConfig is a config class meant to be used with StateDictType.SHARDED_STATE_DICT.

_use_dtensor (bool) – If True, then FSDP saves the state dict values as DTensor, and if False, then FSDP saves them as ShardedTensor. (Default: False)

_use_dtensor is a private field of ShardedStateDictConfig and it is used by FSDP to determine the type of state dict values. Users should not manually modify _use_dtensor.

OptimStateDictConfig is the base class for all optim_state_dict configuration classes. Users should instantiate a child class (e.g. FullOptimStateDictConfig) in order to configure settings for the corresponding optim_state_dict type supported by FSDP.

offload_to_cpu (bool) – If True, then FSDP offloads the state dict’s tensor values to CPU, and if False, then FSDP keeps them on the original device (which is GPU unless parameter CPU offloading is enabled). (Default: True)

rank0_only (bool) – If True, then only rank 0 saves the full state dict, and nonzero ranks save an empty dict. If False, then all ranks save the full state dict. (Default: False)

ShardedOptimStateDictConfig is a config class meant to be used with StateDictType.SHARDED_STATE_DICT.

_use_dtensor (bool) – If True, then FSDP saves the state dict values as DTensor, and if False, then FSDP saves them as ShardedTensor. (Default: False)

_use_dtensor is a private field of ShardedOptimStateDictConfig and it is used by FSDP to determine the type of state dict values. Users should not manually modify _use_dtensor.

---

## Distributed Optimizers#

**URL:** https://pytorch.org/docs/stable/distributed.optim.html

**Contents:**
- Distributed Optimizers#

Created On: Mar 01, 2021 | Last Updated On: Jun 16, 2025

Distributed optimizer is not currently supported when using CUDA tensors

torch.distributed.optim exposes DistributedOptimizer, which takes a list of remote parameters (RRef) and runs the optimizer locally on the workers where the parameters live. The distributed optimizer can use any of the local optimizer Base class to apply the gradients on each worker.

DistributedOptimizer takes remote references to parameters scattered across workers and applies the given optimizer locally for each parameter.

This class uses get_gradients() in order to retrieve the gradients for specific parameters.

Concurrent calls to step(), either from the same or different clients, will be serialized on each worker – as each worker’s optimizer can only work on one set of gradients at a time. However, there is no guarantee that the full forward-backward-optimizer sequence will execute for one client at a time. This means that the gradients being applied may not correspond to the latest forward pass executed on a given worker. Also, there is no guaranteed ordering across workers.

DistributedOptimizer creates the local optimizer with TorchScript enabled by default, so that optimizer updates are not blocked by the Python Global Interpreter Lock (GIL) in the case of multithreaded training (e.g. Distributed Model Parallel). This feature is currently enabled for most optimizers. You can also follow the recipe in PyTorch tutorials to enable TorchScript support for your own custom optimizers.

optimizer_class (optim.Optimizer) – the class of optimizer to instantiate on each worker.

params_rref (list[RRef]) – list of RRefs to local or remote parameters to optimize.

args – arguments to pass to the optimizer constructor on each worker.

kwargs – arguments to pass to the optimizer constructor on each worker.

Performs a single optimization step.

This will call torch.optim.Optimizer.step() on each worker containing parameters to be optimized, and will block until all workers return. The provided context_id will be used to retrieve the corresponding context that contains the gradients that should be applied to the parameters.

context_id – the autograd context id for which we should run the optimizer step.

Wraps an arbitrary torch.optim.Optimizer and runs post-local SGD, This optimizer runs local optimizer at every step. After the warm-up stage, it averages parameters periodically after the local optimizer is applied.

optim (Optimizer) – The local optimizer.

averager (ModelAverager) – A model averager instance to run post-localSGD algorithm.

This is the same as torch.optim.Optimizer load_state_dict(), but also restores model averager’s step value to the one saved in the provided state_dict.

If there is no "step" entry in state_dict, it will raise a warning and initialize the model averager’s step to 0.

This is the same as torch.optim.Optimizer state_dict(), but adds an extra entry to record model averager’s step to the checkpoint to ensure reload does not cause unnecessary warm up again.

Performs a single optimization step (parameter update).

Wrap an arbitrary optim.Optimizer and shards its states across ranks in the group.

The sharing is done as described by ZeRO.

The local optimizer instance in each rank is only responsible for updating approximately 1 / world_size parameters and hence only needs to keep 1 / world_size optimizer states. After parameters are updated locally, each rank will broadcast its parameters to all other peers to keep all model replicas in the same state. ZeroRedundancyOptimizer can be used in conjunction with torch.nn.parallel.DistributedDataParallel to reduce per-rank peak memory consumption.

ZeroRedundancyOptimizer uses a sorted-greedy algorithm to pack a number of parameters at each rank. Each parameter belongs to a single rank and is not divided among ranks. The partition is arbitrary and might not match the parameter registration or usage order.

params (Iterable) – an Iterable of torch.Tensor s or dict s giving all parameters, which will be sharded across ranks.

optimizer_class (torch.nn.Optimizer) – the class of the local optimizer.

process_group (ProcessGroup, optional) – torch.distributed ProcessGroup (default: dist.group.WORLD initialized by torch.distributed.init_process_group()).

parameters_as_bucket_view (bool, optional) – if True, parameters are packed into buckets to speed up communication, and param.data fields point to bucket views at different offsets; if False, each individual parameter is communicated separately, and each params.data stays intact (default: False).

overlap_with_ddp (bool, optional) – if True, step() is overlapped with DistributedDataParallel ‘s gradient synchronization; this requires (1) either a functional optimizer for the optimizer_class argument or one with a functional equivalent and (2) registering a DDP communication hook constructed from one of the functions in ddp_zero_hook.py; parameters are packed into buckets matching those in DistributedDataParallel, meaning that the parameters_as_bucket_view argument is ignored. If False, step() runs disjointly after the backward pass (per normal). (default: False)

**defaults – any trailing arguments, which are forwarded to the local optimizer.

Currently, ZeroRedundancyOptimizer requires that all of the passed-in parameters are the same dense type.

If you pass overlap_with_ddp=True, be wary of the following: Given the way that overlapping DistributedDataParallel with ZeroRedundancyOptimizer is currently implemented, the first two or three training iterations do not perform parameter updates in the optimizer step, depending on if static_graph=False or static_graph=True, respectively. This is because it needs information about the gradient bucketing strategy used by DistributedDataParallel, which is not finalized until the second forward pass if static_graph=False or until the third forward pass if static_graph=True. To adjust for this, one option is to prepend dummy inputs.

ZeroRedundancyOptimizer is experimental and subject to change.

Add a parameter group to the Optimizer ‘s param_groups.

This can be useful when fine tuning a pre-trained network, as frozen layers can be made trainable and added to the Optimizer as training progresses.

param_group (dict) – specifies the parameters to be optimized and group-specific optimization options.

This method handles updating the shards on all partitions but needs to be called on all ranks. Calling this on a subset of the ranks will cause the training to hang because communication primitives are called depending on the managed parameters and expect all the ranks to participate on the same set of parameters.

Consolidate a list of state_dict s (one per rank) on the target rank.

to (int) – the rank that receives the optimizer states (default: 0).

RuntimeError – if overlap_with_ddp=True and this method is called before this ZeroRedundancyOptimizer instance has been fully initialized, which happens once DistributedDataParallel gradient buckets have been rebuilt.

This needs to be called on all ranks.

Return default device.

Return the ZeRO join hook.

It enables training on uneven inputs by shadowing the collective communications in the optimizer step.

Gradients must be properly set before this hook is called.

kwargs (dict) – a dict containing any keyword arguments to modify the behavior of the join hook at run time; all Joinable instances sharing the same join context manager are forwarded the same value for kwargs.

This hook does not support any keyword arguments; i.e. kwargs is unused.

Return process group.

Load the state pertaining to the given rank from the input state_dict, updating the local optimizer as needed.

state_dict (dict) – optimizer state; should be an object returned from a call to state_dict().

RuntimeError – if overlap_with_ddp=True and this method is called before this ZeroRedundancyOptimizer instance has been fully initialized, which happens once DistributedDataParallel gradient buckets have been rebuilt.

Return the last global optimizer state known to this rank.

RuntimeError – if overlap_with_ddp=True and this method is called before this ZeroRedundancyOptimizer instance has been fully initialized, which happens once DistributedDataParallel gradient buckets have been rebuilt; or if this method is called without a preceding call to consolidate_state_dict().

Perform a single optimizer step and syncs parameters across all ranks.

closure (Callable) – a closure that re-evaluates the model and returns the loss; optional for most optimizers.

Optional loss depending on the underlying local optimizer.

Any extra parameters are passed to the base optimizer as-is.

---

## Torch Distributed Elastic#

**URL:** https://pytorch.org/docs/stable/distributed.elastic.html

**Contents:**
- Torch Distributed Elastic#
- Get Started#
- Documentation#

Created On: Jun 16, 2025 | Last Updated On: Jul 25, 2025

Makes distributed PyTorch fault-tolerant and elastic.

---

## Pipeline Parallelism#

**URL:** https://pytorch.org/docs/stable/distributed.pipelining.html

**Contents:**
- Pipeline Parallelism#
- Why Pipeline Parallel?#
- What is torch.distributed.pipelining?#
- Step 1: build PipelineStage#
- Step 2: use PipelineSchedule for execution#
- Options for Splitting a Model#
  - Option 1: splitting a model manually#
  - Option 2: splitting a model automatically#
- Hugging Face Examples#
- Technical Deep Dive#

Created On: Jun 16, 2025 | Last Updated On: Aug 13, 2025

torch.distributed.pipelining is currently in alpha state and under development. API changes may be possible. It was migrated from the PiPPy project.

Pipeline Parallelism is one of the primitive parallelism for deep learning. It allows the execution of a model to be partitioned such that multiple micro-batches can execute different parts of the model code concurrently. Pipeline parallelism can be an effective technique for:

bandwidth-limited clusters

large model inference

The above scenarios share a commonality that the computation per device cannot hide the communication of conventional parallelism, for example, the weight all-gather of FSDP.

While promising for scaling, pipelining is often difficult to implement because it needs to partition the execution of a model in addition to model weights. The partitioning of execution often requires intrusive code changes to your model. Another aspect of complexity comes from scheduling micro-batches in a distributed environment, with data flow dependency considered.

The pipelining package provides a toolkit that does said things automatically which allows easy implementation of pipeline parallelism on general models.

It consists of two parts: a splitting frontend and a distributed runtime. The splitting frontend takes your model code as-is, splits it up into “model partitions”, and captures the data-flow relationship. The distributed runtime executes the pipeline stages on different devices in parallel, handling things like micro-batch splitting, scheduling, communication, and gradient propagation, etc.

Overall, the pipelining package provides the following features:

Splitting of model code based on simple specification.

Rich support for pipeline schedules, including GPipe, 1F1B, Interleaved 1F1B and Looped BFS, and providing the infrastructure for writing customized schedules.

First-class support for cross-host pipeline parallelism, as this is where PP is typically used (over slower interconnects).

Composability with other PyTorch parallel techniques such as data parallel (DDP, FSDP) or tensor parallel. The TorchTitan project demonstrates a “3D parallel” application on the Llama model.

Before we can use a PipelineSchedule, we need to create PipelineStage objects that wrap the part of the model running in that stage. The PipelineStage is responsible for allocating communication buffers and creating send/recv ops to communicate with its peers. It manages intermediate buffers e.g. for the outputs of forward that have not been consumed yet, and it provides a utility for running the backwards for the stage model.

A PipelineStage needs to know the input and output shapes for the stage model, so that it can correctly allocate communication buffers. The shapes must be static, e.g. at runtime the shapes can not change from step to step. A class PipeliningShapeError will be raised if runtime shapes do not match the expected shapes. When composing with other paralleisms or applying mixed precision, these techniques must be taken into account so the PipelineStage knows the correct shape (and dtype) for the output of the stage module at runtime.

Users may construct a PipelineStage instance directly, by passing in an nn.Module representing the portion of the model that should run on the stage. This may require changes to the original model code. See the example in Option 1: splitting a model manually.

Alternatively, the splitting frontend can use graph partitioning to split your model into a series of nn.Module automatically. This technique requires the model is traceable with torch.Export. Composability of the resulting nn.Module with other parallelism techniques is experimental, and may require some workarounds. Usage of this frontend may be more appealing if the user cannot easily change the model code. See Option 2: splitting a model automatically for more information.

We can now attach the PipelineStage to a pipeline schedule, and run the schedule with input data. Here is a GPipe example:

Note that the above code needs to be launched for each worker, thus we use a launcher service to launch multiple processes:

To directly construct a PipelineStage, the user is responsible for providing a single nn.Module instance that owns the relevant nn.Parameters and nn.Buffers, and defines a forward() method that executes the operations relevant for that stage. For example, a condensed version of the Transformer class defined in Torchtitan shows a pattern of building an easily partitionable model.

A model defined in this manner can be easily configured per stage by first initializing the whole model (using meta-device to avoid OOM errors), deleting undesired layers for that stage, and then creating a PipelineStage that wraps the model. For example:

When composing with other Data or Model parallelism techniques, output_args may also be required, if the output shape/dtype of the model chunk will be affected.

If you have a full model and do not want to spend time on modifying it into a sequence of “model partitions”, the pipeline API is here to help. Here is a brief example:

If we print the model, we can see multiple hierarchies, which makes it hard to split by hand:

Let us see how the pipeline API works:

The pipeline API splits your model given a split_spec, where SplitPoint.BEGINNING stands for adding a split point before execution of certain submodule in the forward function, and similarly, SplitPoint.END for split point after such.

If we print(pipe), we can see:

The “model partitions” are represented by submodules (submod_0, submod_1), each of which is reconstructed with original model operations, weights and hierarchies. In addition, a “root-level” forward function is reconstructed to capture the data flow between those partitions. Such data flow will be replayed by the pipeline runtime later, in a distributed fashion.

The Pipe object provides a method for retrieving the “model partitions”:

The returned stage_mod is a nn.Module, with which you can create an optimizer, save or load checkpoints, or apply other parallelisms.

Pipe also allows you to create a distributed stage runtime on a device given a ProcessGroup:

Alternatively, if you would like to build the stage runtime later after some modification to the stage_mod, you can use a functional version of the build_stage API. For example:

The pipeline frontend uses a tracer (torch.export) to capture your model into a single graph. If your model is not full-graph’able, you can use our manual frontend below.

In the PiPPy repo where this package was original created, we kept examples based on unmodified Hugging Face models. See the examples/huggingface directory.

First, the pipeline API turns our model into a directed acyclic graph (DAG) by tracing the model. It traces the model using torch.export – a PyTorch 2 full-graph capturing tool.

Then, it groups together the operations and parameters needed by a stage into a reconstructed submodule: submod_0, submod_1, …

Different from conventional submodule access methods like Module.children(), the pipeline API does not only cut the module structure of your model, but also the forward function of your model.

This is necessary because model structure like Module.children() merely captures information during Module.__init__(), and does not capture any information about Module.forward(). Said differently, Module.children() lacks information about the following aspects key to pipelininig:

Execution order of child modules in forward

Activation flows between child modules

Whether there are any functional operators between child modules (for example, relu or add operations will not be captured by Module.children()).

The pipeline API, on the contrary, makes sure that the forward behavior is truly preserved. It also captures the activation flow between the partitions, helping the distributed runtime to make correct send/receive calls without human intervention.

Another flexibility of the pipeline API is that split points can be at arbitrary levels within your model hierarchy. In the split partitions, the original model hierarchy related to that partition will be reconstructed at no cost to you. At a result, fully-qualified names (FQNs) pointing to a submodule or parameter would be still valid, and services that relies on FQNs (such as FSDP, TP or checkpointing) can still run with your partitioned modules with almost zero code change.

You can implement your own pipeline schedule by extending one of the following two class:

PipelineScheduleSingle

PipelineScheduleMulti

PipelineScheduleSingle is for schedules that assigns only one stage per rank. PipelineScheduleMulti is for schedules that assigns multiple stages per rank.

For example, ScheduleGPipe and Schedule1F1B are subclasses of PipelineScheduleSingle. Whereas, ScheduleInterleaved1F1B, ScheduleLoopedBFS, ScheduleInterleavedZeroBubble, and ScheduleZBVZeroBubble are subclasses of PipelineScheduleMulti.

You can turn on additional logging using the TORCH_LOGS environment variable from torch._logging:

TORCH_LOGS=+pp will display logging.DEBUG messages and all levels above it.

TORCH_LOGS=pp will display logging.INFO messages and above.

TORCH_LOGS=-pp will display logging.WARNING messages and above.

The following set of APIs transform your model into a pipeline representation.

Enum representing the points at which a split can occur in the execution of a submodule. :ivar BEGINNING: Represents adding a split point before the execution of a certain submodule in the forward function. :ivar END: Represents adding a split point after the execution of a certain submodule in the forward function.

Split a module based on a specification.

See Pipe for more details.

module (Module) – The module to be split.

mb_args (tuple[Any, ...]) – Example positional inputs, in micro-batch form.

mb_kwargs (Optional[dict[str, Any]]) – Example keyword inputs, in micro-batch form. (default: None)

split_spec (Optional[dict[str, torch.distributed.pipelining._IR.SplitPoint]]) – A dictionary using submodule names as split marker. (default: None)

split_policy (Optional[Callable[[GraphModule], GraphModule]]) – The policy to use for splitting the module. (default: None)

A pipeline representation of class Pipe.

pipe_split is a special operator that is used to mark the boundary between stages in a module. It is used to split the module into stages. It is a no-op if your annotated module is run eagerly.

The above example will be split into two stages.

Class used to specify chunking of inputs

Given a sequence of args and kwargs, split them into a number of chunks according to their respective chunking specs.

args (tuple[Any, ...]) – Tuple of args

kwargs (Optional[dict[str, Any]]) – Dict of kwargs

chunks (int) – Number of chunks to split the args and kwargs into

args_chunk_spec (Optional[tuple[torch.distributed.pipelining.microbatch.TensorChunkSpec, ...]]) – chunking specs for args, in same shape as args

kwargs_chunk_spec (Optional[dict[str, torch.distributed.pipelining.microbatch.TensorChunkSpec]]) – chunking specs for kwargs, in same shape as kwargs

List of sharded args kwargs_split: List of sharded kwargs

Given a list of chunks, merge them into a single value according to the chunk spec.

chunks (list[Any]) – list of chunks

chunk_spec – Chunking spec for the chunks

A class representing a pipeline stage in a pipeline parallelism setup.

PipelineStage assumes sequential partitioning of the model, i.e. the model is split into chunks where outputs from one chunk feed into inputs of the next chunk, with no skip connections.

PipelineStage performs runtime shape/dtype inference automatically by propagating the outputs from stage0 to stage1 and so forth, in linear order. To bypass shape inference, pass the input_args and output_args to each PipelineStage instance.

submodule (nn.Module) – The PyTorch module wrapped by this stage.

stage_index (int) – The ID of this stage.

num_stages (int) – The total number of stages.

device (torch.device) – The device where this stage is located.

input_args (Union[torch.Tensor, Tuple[torch.tensor]], optional) – The input arguments for the submodule.

output_args (Union[torch.Tensor, Tuple[torch.tensor]], optional) – The output arguments for the submodule.

group (dist.ProcessGroup, optional) – The process group for distributed training. If None, default group.

dw_builder (Optional[Callable[[], Callable[..., None]]) – If provided, dw_builder will build a new dw_runner function that will the W action (input weights) for F, I, W (Fwd, Input, Weight) zero bubble schedules.

Create a pipeline stage given a stage_module to be wrapped by this stage and pipeline information.

stage_module (torch.nn.Module) – the module to be wrapped by this stage

stage_index (int) – the index of this stage in the pipeline

pipe_info (PipeInfo) – information about the pipeline, can be retrieved by pipe.info()

device (torch.device) – the device to be used by this stage

group (Optional[dist.ProcessGroup]) – the process group to be used by this stage

a pipeline stage that can run with PipelineSchedules.

The GPipe schedule. Will go through all the microbatches in a fill-drain manner.

The 1F1B schedule. Will perform one forward and one backward on the microbatches in steady state.

The Interleaved 1F1B schedule. See https://arxiv.org/pdf/2104.04473 for details. Will perform one forward and one backward on the microbatches in steady state and supports multiple stages per rank. When microbatches are ready for multiple local stages, Interleaved 1F1B prioritizes the earlier microbatch (also called “depth first”).

This schedule is mostly similar to the original paper. It differs by being relaxing the requirement of num_microbatch % pp_size == 0. Using the flex_pp schedule, we will have num_rounds = max(1, n_microbatches // pp_group_size) and it works as long as n_microbatches % num_rounds is 0. As a few examples, support

pp_group_size = 4, n_microbatches = 10. We will have num_rounds = 2 and n_microbatches % 2 is 0.

pp_group_size = 4, n_microbatches = 3. We will have num_rounds = 1 and n_microbatches % 1 is 0.

Breadth-First Pipeline Parallelism. See https://arxiv.org/abs/2211.05953 for details. Similar to Interleaved 1F1B, Looped BFS supports multiple stages per rank. What is different is that when microbatches are ready for multiple local stages, Loops BFS will prioritizes the earlier stage, running all available microbatches at once.

The Interleaved Zero Bubble schedule. See https://arxiv.org/pdf/2401.10241 for details. Will perform one forward and one backward on inputs for the microbatches in steady state and supports multiple stages per rank. Uses the backward for weights to fill in the pipeline bubble.

In particular this is implementing the ZB1P schedule in the paper.

The Zero Bubble schedule (ZBV variant). See https://arxiv.org/pdf/2401.10241 Section 6 for details.

This schedules requires exactly two stages per rank.

This schedule will perform one forward and one backward on inputs for the microbatches in steady state and supports multiple stages per rank. Uses backward with respect to weights to fill in the pipeline bubble.

This ZB-V schedule would have the “zero bubble” property only if time forward == time backward input == time backward weights. In practice, this is not likely true for real models so alternatively a greedy scheduler could be implemented for unequal/unbalanced time.

The DualPipeV schedule. A more efficient schedule variant based on the DualPipe schedule introduced by DeepSeek in https://arxiv.org/pdf/2412.19437

Based on the open sourced code from deepseek-ai/DualPipe

Base class for single-stage schedules. Implements the step method. Derived classes should implement _step_microbatches.

Gradients are scaled by num_microbatches depending on the scale_grads argument, defaulting to True. This setting should match the configuration of your loss_fn, which may either average losses (scale_grads=True) or sum losses (scale_grads=False).

Run one iteration of the pipeline schedule with whole-batch input. Will chunk the input into microbatches automatically, and go through the microbatches according to the schedule implementation.

args: positional arguments to the model (as in non-pipeline case). kwargs: keyword arguments to the model (as in non-pipeline case). target: target for the loss function. losses: a list to store the losses for each microbatch.

Base class for multi-stage schedules. Implements the step method.

Gradients are scaled by num_microbatches depending on the scale_grads argument, defaulting to True. This setting should match the configuration of your loss_fn, which may either average losses (scale_grads=True) or sum losses (scale_grads=False).

Run one iteration of the pipeline schedule with whole-batch input. Will chunk the input into microbatches automatically, and go through the microbatches according to the schedule implementation.

args: positional arguments to the model (as in non-pipeline case). kwargs: keyword arguments to the model (as in non-pipeline case). target: target for the loss function. losses: a list to store the losses for each microbatch.

---

## Tensor Parallelism - torch.distributed.tensor.parallel#

**URL:** https://pytorch.org/docs/stable/distributed.tensor.parallel.html

**Contents:**
- Tensor Parallelism - torch.distributed.tensor.parallel#

Created On: Jun 13, 2025 | Last Updated On: Jun 13, 2025

Tensor Parallelism(TP) is built on top of the PyTorch DistributedTensor (DTensor)[https://github.com/pytorch/pytorch/blob/main/torch/distributed/tensor/README.md] and provides different parallelism styles: Colwise, Rowwise, and Sequence Parallelism.

Tensor Parallelism APIs are experimental and subject to change.

The entrypoint to parallelize your nn.Module using Tensor Parallelism is:

Apply Tensor Parallelism in PyTorch by parallelizing modules or sub-modules based on a user-specified plan.

We parallelize module or sub_modules based on a parallelize_plan. The parallelize_plan contains ParallelStyle, which indicates how user wants the module or sub_module to be parallelized.

User can also specify different parallel style per module fully qualified name (FQN).

Note that parallelize_module only accepts a 1-D DeviceMesh, if you have a 2-D or N-D DeviceMesh, slice the DeviceMesh to a 1-D sub DeviceMesh first then pass to this API(i.e. device_mesh["tp"])

module (nn.Module) – Module to be parallelized.

device_mesh (DeviceMesh, optional) – Object which describes the mesh topology of devices for the DTensor. If not specified, the call must be under a DeviceMesh context.

parallelize_plan (Union[ParallelStyle, Dict[str, ParallelStyle]], optional) – The plan used to parallelize the module. It can be either a ParallelStyle object which contains how we prepare input/output for Tensor Parallelism or it can be a dict of module FQN and its corresponding ParallelStyle object. If not specified, the call will do nothing at the moment.

src_data_rank (int, optional) – the rank of the source data for the logical/global tensor, it is used by distribute_tensor() to scatter/broadcast the shards/replicas to other ranks. By default, we use group_rank=0 on each DeviceMesh dimension as the source data to preserve the single-device semantic. If passing None explicitly, parallelize_module() simply uses its local data instead of trying to preserve the single-device semantic via scatter/broadcast. Default: 0

A nn.Module object parallelized.

For complex module architecture like Attention, MLP layers, we recommend composing different ParallelStyles together (i.e. ColwiseParallel and RowwiseParallel) and pass as a parallelize_plan, to achieves the desired sharding computation.

Tensor Parallelism supports the following parallel styles:

Partition a compatible nn.Module in a column-wise fashion. Currently supports nn.Linear and nn.Embedding. Users can compose it together with RowwiseParallel to achieve the sharding of more complicated modules. (i.e. MLP, Attention)

input_layouts (Placement, optional) – The DTensor layout of input tensor for the nn.Module, this is used to annotate the input tensor to become a DTensor. If not specified, we assume the input tensor to be replicated.

output_layouts (Placement, optional) – The DTensor layout of the output for the nn.Module, this is used to ensure the output of the nn.Module with the user desired layout. If not specified, the output tensor is sharded on the last dimension.

use_local_output (bool, optional) – Whether to use local torch.Tensor instead of DTensor for the module output, default: True.

A ParallelStyle object that represents Colwise sharding of the nn.Module.

By default ColwiseParallel output is sharded on the last dimension if the output_layouts not specified, if there’re operators that require specific tensor shape (i.e. before the paired RowwiseParallel), keep in mind that if the output is sharded the operator might need to be adjusted to the sharded size.

Partition a compatible nn.Module in a row-wise fashion. Currently supports nn.Linear and nn.Embedding. Users can compose it with ColwiseParallel to achieve the sharding of more complicated modules. (i.e. MLP, Attention)

input_layouts (Placement, optional) – The DTensor layout of input tensor for the nn.Module, this is used to annotate the input tensor to become a DTensor. If not specified, we assume the input tensor to be sharded on the last dimension.

output_layouts (Placement, optional) – The DTensor layout of the output for the nn.Module, this is used to ensure the output of the nn.Module with the user desired layout. If not specified, the output tensor is replicated.

use_local_output (bool, optional) – Whether to use local torch.Tensor instead of DTensor for the module output, default: True.

A ParallelStyle object that represents Rowwise sharding of the nn.Module.

SequenceParallel replicates a compatible nn.Module parameters and runs the sharded computation with input sharded on the sequence dimension. This currently supports nn.LayerNorm, nn.Dropout, and the RMSNorm python implementation

This style implements the operation that is described in the paper Reducing Activation Recomputation in Large Transformer Models

If the input passed in to this nn.Module is a torch.Tensor, it assumes that the input is already sharded on the sequence dimension and converts the input to a DTensor sharded on the sequence dimension. If the input passed in to this nn.Module is already a DTensor but is not sharded on the sequence dimension, it would redistribute the input to be sharded on the sequence dimension.

The output of the nn.Module will be sharded on the sequence dimension.

sequence_dim (int, optional) – The sequence dimension of the input tensor for the nn.Module, this is used to annotate the input tensor to become a DTensor that is sharded on the sequence dimension, default: 1.

use_local_output (bool, optional) – Whether to use local torch.Tensor instead of DTensor for the module output, default: False.

A ParallelStyle object that represents Sequence Parallel of the nn.Module.

SequenceParallel style assumes ones initialization if there are weights in the nn.Module (i.e. nn.LayerNorm or RMSNorm, and they by default have ones initialization). If you have custom inits for the weights on those modules, you need to broadcast the weights before/after parallelizing to ensure that they are replicated.

To simply configure the nn.Module’s inputs and outputs with DTensor layouts and perform necessary layout redistributions, without distribute the module parameters to DTensors, the following ParallelStyle s can be used in the parallelize_plan when calling parallelize_module:

Configure the nn.Module’s inputs to convert the input tensors of the nn.Module to DTensors at runtime according to input_layouts, and perform layout redistribution according to the desired_input_layouts.

input_layouts (Union[Placement, Tuple[Optional[Placement]]]) – The DTensor layouts of input tensors for the nn.Module, this is used to convert the input tensors to DTensors. If some inputs are not torch.Tensor or no need to convert to DTensors, None need to be specified as a placeholder. default: None.

desired_input_layouts (Union[Placement, Tuple[Optional[Placement]]]) – The desired DTensor layout of input tensors for the nn.Module, this is used to ensure the inputs of the nn.Module have the desired DTensor layouts. This argument needs to have the same length with input_layouts. default: None.

input_kwarg_layouts (Dict[str, Placement]) – The DTensor layouts of input kwargs for the nn.Module, this is used to convert the input kwarg tensors to DTensors. default: None

desired_input_kwarg_layouts – (Dict[str, Placement]): The desired DTensor layout of input kwargs for the nn.Module, this is used to ensure the inputs of the nn.Module have the desired DTensor layouts. default: None.

use_local_output (bool, optional) – Whether to use local torch.Tensor instead of DTensor for the module inputs, default: False.

A ParallelStyle object that prepares the sharding layouts of the nn.Module’s inputs.

Configure the nn.Module’s outputs to convert the output tensors of the nn.Module to DTensors at runtime according to output_layouts, and perform layout redistribution according to the desired_output_layouts.

output_layouts (Union[Placement, Tuple[Placement]]) – The DTensor layouts of output tensors for the nn.Module, this is used to convert the output tensors to DTensors if they are torch.Tensor. If some outputs are not torch.Tensor or no need to convert to DTensors, None need to be specified as a placeholder.

desired_output_layouts (Union[Placement, Tuple[Placement]]) – The desired DTensor layouts of output tensors for the nn.Module, this is used to ensure the outputs of the nn.Module have the desired DTensor layouts.

use_local_output (bool, optional) – Whether to use local torch.Tensor instead of DTensor for the module outputs, default: True.

A ParallelStyle object that prepares the sharding layouts of the nn.Module’s outputs.

Configure the nn.Module’s inputs (and outputs) to convert the input tensors (and output tensors, respectively) of the nn.Module to DTensors at runtime according to input_layouts (and output_layouts, respectively), and perform layout redistribution according to the desired_input_layouts (and desired_output_layouts, respectively). This is a combination of PrepareModuleInput and PrepareModuleOutput.

input_layouts (Union[Placement, Tuple[Optional[Placement]]]) – The DTensor layouts of input tensors for the nn.Module, this is used to convert the input tensors to DTensors. If some inputs are not torch.Tensor or no need to convert to DTensors, None need to be specified as a placeholder. default: None.

desired_input_layouts (Union[Placement, Tuple[Optional[Placement]]]) – The desired DTensor layout of input tensors for the nn.Module, this is used to ensure the inputs of the nn.Module have the desired DTensor layouts. This argument needs to have the same length with input_layouts. default: None.

input_kwarg_layouts (Dict[str, Placement]) – The DTensor layouts of input kwargs for the nn.Module, this is used to convert the input kwarg tensors to DTensors. default: None

desired_input_kwarg_layouts – (Dict[str, Placement]): The desired DTensor layout of input kwargs for the nn.Module, this is used to ensure the inputs of the nn.Module have the desired DTensor layouts. default: None.

use_local_input (bool, optional) – Whether to use local torch.Tensor instead of DTensor for the module inputs, default: False.

output_layouts (Union[Placement, Tuple[Placement]]) – The DTensor layouts of output tensors for the nn.Module, this is used to convert the output tensors to DTensors if they are torch.Tensor. If some outputs are not torch.Tensor or no need to convert to DTensors, None need to be specified as a placeholder.

desired_output_layouts (Union[Placement, Tuple[Placement]]) – The desired DTensor layouts of output tensors for the nn.Module, this is used to ensure the outputs of the nn.Module have the desired DTensor layouts.

use_local_output (bool, optional) – Whether to use local torch.Tensor instead of DTensor for the module outputs, default: True.

A ParallelStyle object that prepares the sharding layouts of the nn.Module’s inputs and outputs.

when using the Shard(dim) as the input/output layouts for the above ParallelStyle s, we assume the input/output activation tensors are evenly sharded on the tensor dimension dim on the DeviceMesh that TP operates on. For instance, since RowwiseParallel accepts input that is sharded on the last dimension, it assumes the input tensor has already been evenly sharded on the last dimension. For the case of uneven sharded activation tensors, one could pass in DTensor directly to the partitioned modules, and use use_local_output=False to return DTensor after each ParallelStyle, where DTensor could track the uneven sharding information.

For models like Transformer, we recommend users to use ColwiseParallel and RowwiseParallel together in the parallelize_plan for achieve the desired sharding for the entire model (i.e. Attention and MLP).

Parallelized cross-entropy loss computation (loss parallelism), is supported via the following context manager:

A context manager that enables loss parallelism, where efficient parallelized loss computation can be performed when the input is sharded on the class dimension. Currently only the cross-entropy loss is supported.

Within this context manager, one can use cross_entropy() or CrossEntropyLoss as usual, with the following assumptions on the input parameters. The corresponding backward() call, if any, also needs to happen under this context manager.

input (DTensor) – Input logits. Assumed to be sharded on the class dimension.

target (Union[torch.Tensor, DTensor]) – Must be ground truth class indices (class probabilities currently not supported). Assumed to be replicated across the DeviceMesh.

weight (Union[torch.Tensor, DTensor], optional) – If given, assumed to be replicated across the DeviceMesh.

label_smoothing – Currently not supported.

A replicated DTensor.

A sharded DTensor is manually created here to showcase the usage. In practice, it is usually the output of a TP module.

---
