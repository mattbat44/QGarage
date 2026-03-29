from qgarage.core.base_app import BaseApp, InputType, OutputType


class FeatureCounterApp(BaseApp):
    """Example app demonstrating declarative output specs.

    This app shows how to use add_output() to expose results to the
    Processing framework, enabling Model Builder integration and
    batch processing workflows.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Inputs
        self.add_input(
            "input_layer",
            "Input Layer",
            InputType.VECTOR_LAYER,
            tooltip="Vector layer to analyze"
        )
        self.add_input(
            "export_stats",
            "Export Statistics",
            InputType.BOOLEAN,
            default=False,
            tooltip="Export statistics to a text file"
        )
        self.add_input(
            "output_folder",
            "Output Folder",
            InputType.FOLDER_PATH,
            required=False,
            tooltip="Folder for statistics file (required if Export Statistics is checked)"
        )

        # Outputs - these are exposed to the Processing framework
        self.add_output(
            "feature_count",
            "Feature Count",
            OutputType.INTEGER,
            description="Total number of features in the input layer"
        )
        self.add_output(
            "layer_name",
            "Layer Name",
            OutputType.STRING,
            description="Name of the analyzed layer"
        )
        self.add_output(
            "statistics_file",
            "Statistics File",
            OutputType.FILE,
            description="Path to the exported statistics file (if exported)"
        )

    def validate_inputs(self, inputs):
        """Validate that output folder is provided when export is requested."""
        if inputs.get("export_stats") and not inputs.get("output_folder"):
            return "Output folder is required when 'Export Statistics' is enabled"
        return None

    def execute_logic(self, inputs):
        """Count features and optionally export statistics."""
        layer = inputs["input_layer"]
        export_stats = inputs.get("export_stats", False)
        output_folder = inputs.get("output_folder", "")

        # Get basic statistics
        feature_count = layer.featureCount()
        layer_name = layer.name()

        self.log(f"Analyzing layer: {layer_name}")
        self.log(f"Feature count: {feature_count}")

        result = {
            "status": "success",
            "message": f"Counted {feature_count} features in '{layer_name}'",
            "feature_count": feature_count,
            "layer_name": layer_name,
        }

        # Optionally export to file
        if export_stats and output_folder:
            import os
            from datetime import datetime

            stats_file = os.path.join(
                output_folder,
                f"{layer_name}_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )

            stats_content = f"""Feature Count Statistics
========================

Layer Name: {layer_name}
Feature Count: {feature_count}
CRS: {layer.crs().authid()}
Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

            with open(stats_file, "w", encoding="utf-8") as f:
                f.write(stats_content)

            self.log(f"Statistics exported to: {stats_file}")
            result["statistics_file"] = stats_file
            result["message"] += f". Statistics exported to {os.path.basename(stats_file)}"
        else:
            # Return empty string when not exporting (output is still declared)
            result["statistics_file"] = ""

        return result
