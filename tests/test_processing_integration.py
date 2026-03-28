"""Tests for QGIS Processing framework integration."""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from qgarage.core.base_app import BaseApp, InputType
from qgarage.processing.parameter_mapper import create_processing_parameter, extract_parameter_value
from qgarage.processing.algorithm_wrapper import BaseAppAlgorithm
from qgarage.processing.processing_provider import QGarageProcessingProvider


# Sample app for testing
class SimpleTestApp(BaseApp):
    """Simple test app with declarative inputs."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input("name", "Name", InputType.STRING, default="Test")
        self.add_input("count", "Count", InputType.INTEGER, default=1, min_value=1, max_value=10)
        self.add_input("enabled", "Enabled", InputType.BOOLEAN, default=True)

    def execute_logic(self, inputs):
        name = inputs.get("name", "")
        count = inputs.get("count", 1)
        enabled = inputs.get("enabled", False)

        message = f"Processed {name} {count} times (enabled={enabled})"
        return {"status": "success", "message": message}


class DynamicTestApp(BaseApp):
    """Dynamic app with custom UI - should NOT be exposed to Processing."""

    def build_dynamic_widget(self):
        from qgis.PyQt.QtWidgets import QWidget
        return QWidget()


def test_parameter_mapper_string():
    """Test STRING input type mapping."""
    from qgarage.core.base_app import InputSpec

    spec = InputSpec(
        key="test_string",
        label="Test String",
        input_type=InputType.STRING,
        default="hello",
    )

    param = create_processing_parameter(spec)
    assert param.name() == "test_string"
    assert param.description() == "Test String"
    assert param.defaultValue() == "hello"


def test_parameter_mapper_integer():
    """Test INTEGER input type mapping."""
    from qgarage.core.base_app import InputSpec
    from qgis.core import QgsProcessingParameterNumber

    spec = InputSpec(
        key="test_int",
        label="Test Integer",
        input_type=InputType.INTEGER,
        default=5,
        min_value=1,
        max_value=100,
    )

    param = create_processing_parameter(spec)
    assert param.name() == "test_int"
    assert param.type() == QgsProcessingParameterNumber.Type.Integer
    assert param.defaultValue() == 5
    assert param.minimum() == 1
    assert param.maximum() == 100


def test_parameter_mapper_boolean():
    """Test BOOLEAN input type mapping."""
    from qgarage.core.base_app import InputSpec

    spec = InputSpec(
        key="test_bool",
        label="Test Boolean",
        input_type=InputType.BOOLEAN,
        default=True,
    )

    param = create_processing_parameter(spec)
    assert param.name() == "test_bool"
    assert param.defaultValue() == True


def test_parameter_mapper_choice():
    """Test CHOICE input type mapping."""
    from qgarage.core.base_app import InputSpec

    spec = InputSpec(
        key="test_choice",
        label="Test Choice",
        input_type=InputType.CHOICE,
        choices=["Option A", "Option B", "Option C"],
        default="Option B",
    )

    param = create_processing_parameter(spec)
    assert param.name() == "test_choice"
    assert param.options() == ["Option A", "Option B", "Option C"]
    assert param.defaultValue() == 1  # Index of "Option B"


def test_algorithm_wrapper_creation():
    """Test BaseAppAlgorithm wrapper creation."""
    app_meta = {
        "id": "test_app",
        "name": "Test App",
        "version": "1.0.0",
        "author": "Test",
        "description": "Test app for processing",
        "tags": ["test"],
    }
    app_dir = Path("/tmp/test_app")

    algorithm = BaseAppAlgorithm(app_meta, app_dir, SimpleTestApp)

    assert algorithm.name() == "test_app"
    assert algorithm.displayName() == "Test App"
    assert algorithm.group() == "Test"
    assert algorithm.groupId() == "test"


def test_algorithm_init_parameters():
    """Test algorithm parameter initialization."""
    app_meta = {
        "id": "test_app",
        "name": "Test App",
        "version": "1.0.0",
        "author": "Test",
        "description": "Test description",
        "tags": ["test"],
    }
    app_dir = Path("/tmp/test_app")

    algorithm = BaseAppAlgorithm(app_meta, app_dir, SimpleTestApp)
    algorithm.initAlgorithm()

    # Check that parameters were created
    param_defs = algorithm.parameterDefinitions()
    assert len(param_defs) == 3

    param_names = [p.name() for p in param_defs]
    assert "name" in param_names
    assert "count" in param_names
    assert "enabled" in param_names


def test_processing_provider_filters_dynamic_apps():
    """Test that Processing provider skips dynamic apps."""
    from qgarage.core.app_registry import AppRegistry, AppEntry
    from unittest.mock import Mock

    # Create mock registry with both declarative and dynamic apps
    registry = Mock(spec=AppRegistry)

    # Declarative app entry
    declarative_meta = {
        "id": "declarative_app",
        "name": "Declarative App",
        "version": "1.0.0",
        "author": "Test",
        "description": "Test",
        "tags": ["test"],
    }
    declarative_instance = SimpleTestApp(
        app_meta=declarative_meta,
        app_dir=Path("/tmp/declarative"),
    )
    declarative_entry = Mock()
    declarative_entry.app_meta = declarative_meta
    declarative_entry.app_dir = Path("/tmp/declarative")
    declarative_entry.instance = declarative_instance

    # Dynamic app entry
    dynamic_meta = {
        "id": "dynamic_app",
        "name": "Dynamic App",
        "version": "1.0.0",
        "author": "Test",
        "description": "Test",
        "tags": ["test"],
    }
    dynamic_instance = DynamicTestApp(
        app_meta=dynamic_meta,
        app_dir=Path("/tmp/dynamic"),
    )
    dynamic_entry = Mock()
    dynamic_entry.app_meta = dynamic_meta
    dynamic_entry.app_dir = Path("/tmp/dynamic")
    dynamic_entry.instance = dynamic_instance

    registry.entries = {
        "declarative_app": declarative_entry,
        "dynamic_app": dynamic_entry,
    }
    registry.load_all = Mock()

    provider = QGarageProcessingProvider(registry)
    provider.loadAlgorithms()

    # Only declarative app should be registered
    algorithms = provider.algorithms()
    assert len(algorithms) == 1
    assert algorithms[0].name() == "declarative_app"


def test_algorithm_process_execution():
    """Test algorithm execution."""
    app_meta = {
        "id": "test_app",
        "name": "Test App",
        "version": "1.0.0",
        "author": "Test",
        "description": "Test",
        "tags": ["test"],
    }
    app_dir = Path("/tmp/test_app")

    algorithm = BaseAppAlgorithm(app_meta, app_dir, SimpleTestApp)
    algorithm.initAlgorithm()

    # Mock parameters, context, and feedback
    parameters = {
        "name": "Alice",
        "count": 3,
        "enabled": True,
    }

    context = Mock()
    feedback = Mock()

    # Mock the parameterAs* methods
    algorithm.parameterAsString = Mock(side_effect=lambda p, k, c: parameters.get(k, ""))
    algorithm.parameterAsInt = Mock(side_effect=lambda p, k, c: parameters.get(k, 0))
    algorithm.parameterAsBool = Mock(side_effect=lambda p, k, c: parameters.get(k, False))

    result = algorithm.processAlgorithm(parameters, context, feedback)

    assert result["status"] == "success"
    assert "Alice" in result["message"]
    assert "3 times" in result["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
