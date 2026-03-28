from qgarage.core.base_app import BaseApp, InputType


class BufferToolApp(BaseApp):
    """Simple buffer tool for demonstration."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input(
            "input_layer",
            "Input Layer",
            InputType.VECTOR_LAYER,
            tooltip="Vector layer to buffer"
        )
        self.add_input(
            "distance",
            "Buffer Distance",
            InputType.FLOAT,
            default=100.0,
            min_value=0.0,
            max_value=10000.0,
            tooltip="Distance in layer units"
        )

    def execute_logic(self, inputs):
        """Execute the buffer operation."""
        layer = inputs.get("input_layer")
        distance = inputs.get("distance", 100.0)

        if not layer:
            return {"status": "error", "message": "No input layer selected"}

        # Simple demonstration - just return success
        return {
            "status": "success",
            "message": f"Would buffer {layer.name()} by {distance} units"
        }
