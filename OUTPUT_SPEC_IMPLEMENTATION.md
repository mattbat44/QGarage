# Output Spec Feature - Implementation Summary

## Overview

This implementation adds declarative output specifications to QGarage apps, enabling their outputs to be properly exposed to the QGIS Processing framework. This makes app outputs available for:

- **Model Builder** - Connect app outputs to other algorithm inputs
- **Batch Processing** - Collect and display outputs across multiple runs
- **Scripting** - Access typed, predictable output values

## Key Features

### 1. Optional and Backward Compatible
- Apps without `add_output()` calls continue to work exactly as before
- The framework always returns `STATUS` and `MESSAGE` outputs for compatibility
- Only explicitly declared outputs are exposed to Processing

### 2. Simple, Declarative API
The output spec API mirrors the existing input spec pattern:

```python
# Inputs
self.add_input("input_layer", "Input Layer", InputType.VECTOR_LAYER)

# Outputs
self.add_output("feature_count", "Feature Count", OutputType.INTEGER)
self.add_output("output_file", "Output File", OutputType.FILE)
```

### 3. Comprehensive Type Support
Supports all common output types:
- Primitives: `STRING`, `INTEGER`, `FLOAT`, `BOOLEAN`
- Paths: `FILE`, `FOLDER`
- Layers: `VECTOR_LAYER`, `RASTER_LAYER`, `ANY_LAYER`

## Implementation Details

### Core Components

1. **OutputType Enum** (`qgarage/core/base_app.py`)
   - Defines supported output types
   - Mirrors InputType for consistency

2. **OutputSpec Dataclass** (`qgarage/core/base_app.py`)
   - Stores output metadata: key, label, type, description
   - Similar structure to InputSpec

3. **BaseApp.add_output()** (`qgarage/core/base_app.py`)
   - Method to register outputs in `__init__()`
   - Stores specs in `_output_specs` list

4. **Processing Provider Updates** (`qgarage/core/processing_provider.py`)
   - `initAlgorithm()`: Registers output parameters via `_build_output()`
   - `processAlgorithm()`: Extracts declared outputs from result dict
   - `_build_output()`: Maps OutputType to QgsProcessingOutput* classes

### Example App

The `feature_counter` app demonstrates:
- Multiple output types (INTEGER, STRING, FILE)
- Optional outputs (statistics_file may be empty)
- Integration with execute_logic return dict

## Usage Pattern

```python
from qgarage.core.base_app import BaseApp, InputType, OutputType


class MyApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Declare inputs
        self.add_input("input_layer", "Input", InputType.VECTOR_LAYER)

        # Declare outputs
        self.add_output("count", "Count", OutputType.INTEGER)
        self.add_output("result_file", "Result", OutputType.FILE)

    def execute_logic(self, inputs):
        # Process...
        return {
            "status": "success",
            "message": "Done",
            "count": 42,
            "result_file": "/path/to/result.csv"
        }
```

## Testing

Added comprehensive tests in `tests/test_processing_provider.py`:
- `test_algorithm_exposes_declared_outputs` - Verifies outputs are registered and returned
- `test_algorithm_without_outputs_maintains_backward_compatibility` - Ensures existing apps work unchanged

## Documentation

Updated `qgarage/QHUB_APP_DEVELOPMENT.instructions.md` with:
- Complete `add_output()` API documentation
- OutputType reference table
- Usage examples
- Important notes about optional nature and backward compatibility

## Migration Guide

### For Existing Apps
No changes required! Existing apps continue to work exactly as before.

### For New Apps
To expose outputs to Processing:

1. Add output declarations in `__init__()`:
   ```python
   self.add_output("my_output", "My Output", OutputType.STRING)
   ```

2. Return the output value in `execute_logic()`:
   ```python
   return {
       "status": "success",
       "my_output": "value"
   }
   ```

3. The output is now available in Model Builder and batch processing!

## Benefits

1. **Model Builder Integration** - Apps can now be chained together in processing models
2. **Type Safety** - Processing framework knows output types at registration time
3. **Discoverability** - Outputs are documented in the Processing toolbox
4. **Automation** - Batch processing can collect and use output values
5. **Backward Compatible** - Zero breaking changes to existing apps
6. **Easy to Use** - Matches familiar `add_input()` pattern

## Future Enhancements

Potential future additions:
- Default values for outputs
- Output validation
- Array/list outputs
- CRS outputs
- More complex output types (multi-layer outputs, etc.)
