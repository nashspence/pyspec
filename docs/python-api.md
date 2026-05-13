# Python API

Use the high-level project functions for most integrations:

```python
from pyspec_contract import compile_project, validate_project

compile_project(".", layers="core,http")
validate_project(".", layers="core,http")
```

Useful lower-level entry points:

```python
from pyspec_contract import (
    ArtifactPolicy,
    ProjectConfig,
    compile_author,
    compile_source,
    expected_artifacts,
    write_agent_prompts,
    write_generated,
)
```

`compile_project` and `validate_project` accept either a layer string such as `"core,ui,web"` or a normalized layer set.
`write_agent_prompts(".", layers="core,http")` writes the PM/design, test, dev, and review prompt templates without requiring a compiled spec.
