# Status

We are applying for the following badges:

## Available

The artifact is publicly available on GitHub at <https://github.com/bloomberg-science/spectra>. The repository includes all source code, build scripts, evaluation infrastructure, and documentation required to use the artifact.

## Functional

The artifact is documented, consistent with the paper, complete, and exercisable:

- **Documented:** The [ARTIFACT_EVALUATION.md](ARTIFACT_EVALUATION.md) provides a getting-started guide, smoke tests, and step-by-step instructions for reproducing all four research questions (Tables 1–4).
- **Consistent:** The artifact produces results consistent with those reported in the paper. Minor variations are documented and explained in the artifact evaluation instructions.
- **Complete:** All experiments from the paper can be reproduced, including syscall inference across multiple tools and configurations, ground-truth comparison via seccomp-BPF enforcement, and incremental refinement technique evaluation.
- **Exercisable:** A self-contained Docker image builds the entire evaluation environment from scratch. The framework supports analyzing arbitrary ELF binaries beyond the evaluation packages.

## Reusable

The artifact is designed for reuse and extension beyond the scope of the paper:

- **Modular tool registry:** New analysis backends can be added with a single class and a `@register_tool` decorator — no changes to the core framework are required.
- **Configurable refinement pipeline:** Each refinement technique (context-sensitive AT-set refinement, data-section splitting, escape analysis, signature matching, constant propagation) can be independently enabled or disabled via tool variants.
- **Arbitrary binary analysis:** The framework is not limited to the 11 evaluation packages. Any ELF binary can be analyzed using `gen_syscall.py` or hardened end-to-end using `harden.py`.
- **Well-structured codebase:** Clear separation between analysis backends, call graph construction, and evaluation infrastructure. Centralized configuration, consistent logging, and a documented code layout facilitate understanding and modification.
