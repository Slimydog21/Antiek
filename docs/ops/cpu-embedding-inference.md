# CPU embedding inference

The backend retains `MemoryDenyWriteExecute`, `NoNewPrivileges` and
`ProtectSystem=strict`. Both sentence-transformer adapters select CPU and
disable PyTorch MKLDNN before model construction. This process-wide setting
remains disabled; request completion does not restore it while another thread
is encoding. Native CPU kernels may be slower than oneDNN.

PyTorch's [MKLDNN control](https://docs.pytorch.org/docs/2.14/notes/mkldnn.html)
selects the native [GELU kernel](https://github.com/pytorch/pytorch/blob/v2.13.0/aten/src/ATen/native/Activation.cpp#L354-L390)
without changing the model, weights or GELU approximation. Historical backend
errors reached GELU with executable-memory denial enabled. That supports a
JIT conflict diagnosis; it does not identify the failing native allocation.

Corpus search captures verified request ownership before dispatching model
loading, encoding and read-only DB use to a worker. That worker closes its own
connection. Model initialization or encode failures return an opaque
`503 embedding_unavailable`, rather than an empty successful search.
Embedding compatibility and account/rights admission remain enforced.

The existing normal CI shards exercise Linux `PR_SET_MDWE`, including a refused
writable-to-executable transition, actual native GELU, and two synthetic inputs
through the real pretrained MiniLM model. It compares weights, vectors,
dimensions and existing fingerprints with the original CPU route. It downloads
public model weights only in CI or an explicitly enabled native control. Other tests cover signed HTTP refusals,
concurrent HTTP responsiveness and cancellation cleanup with controlled model
failures. These controls do not establish a successful production search.

The two adapters' existing fingerprints differ. This repair retains that
distinction and does not rewrite stored embeddings or relax compatibility.
Production model/metadata compatibility and a genuine account search still
require their own verification after Root's normal release.
