from qgarage.core.base_app import BaseApp, InputType


class MergeToolApp(BaseApp):
    """Simple merge tool for demonstration."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input(
            "layer1",
            "First Layer",
            InputType.VECTOR_LAYER,
            tooltip="First vector layer to merge"
        )
        self.add_input(
            "layer2",
            "Second Layer",
            InputType.VECTOR_LAYER,
            tooltip="Second vector layer to merge"
        )

    def execute_logic(self, inputs):
        """Execute the merge operation."""
        layer1 = inputs.get("layer1")
        layer2 = inputs.get("layer2")

        if not layer1 or not layer2:
            return {"status": "error", "message": "Please select both layers"}

        # Simple demonstration - just return success
        return {
            "status": "success",
            "message": f"Would merge {layer1.name()} and {layer2.name()}"
        }
