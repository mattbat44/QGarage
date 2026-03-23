from qhub.core.base_app import BaseApp, InputType


class HelloWorldApp(BaseApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_input(
            "name",
            "Your Name",
            InputType.STRING,
            default="World",
            tooltip="Enter a name to greet",
        )
        self.add_input(
            "repeat",
            "Repeat Count",
            InputType.INTEGER,
            default=1,
            min_value=1,
            max_value=10,
            tooltip="How many times to greet",
        )
        self.add_input(
            "layer",
            "Optional Layer",
            InputType.ANY_LAYER,
            required=False,
            tooltip="Select a layer to report info about",
        )

    def execute_logic(self, inputs):
        name = inputs.get("name", "World")
        repeat = inputs.get("repeat", 1)
        layer = inputs.get("layer")

        greetings = [f"Hello, {name}!" for _ in range(repeat)]
        message = "\n".join(greetings)

        if layer is not None:
            message += f"\n\nSelected layer: {layer.name()}"
            message += f"\nFeature count: {layer.featureCount()}"

        return {"status": "success", "message": message}
