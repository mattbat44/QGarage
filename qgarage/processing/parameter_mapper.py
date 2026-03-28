"""Maps QGarage InputType to QgsProcessingParameter types."""

from qgis.core import (
    QgsProcessing,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)

from ..core.base_app import InputSpec, InputType


def create_processing_parameter(spec: InputSpec):
    """Convert an InputSpec to the appropriate QgsProcessingParameter.

    Args:
        spec: Input specification from a BaseApp

    Returns:
        QgsProcessingParameter instance
    """
    name = spec.key
    description = spec.label
    optional = not spec.required
    default_value = spec.default if not optional else None

    if spec.input_type == InputType.STRING:
        return QgsProcessingParameterString(
            name,
            description,
            defaultValue=default_value or "",
            optional=optional,
        )

    elif spec.input_type == InputType.INTEGER:
        return QgsProcessingParameterNumber(
            name,
            description,
            type=QgsProcessingParameterNumber.Type.Integer,
            defaultValue=default_value if default_value is not None else int(spec.min_value),
            optional=optional,
            minValue=int(spec.min_value),
            maxValue=int(spec.max_value),
        )

    elif spec.input_type == InputType.FLOAT:
        return QgsProcessingParameterNumber(
            name,
            description,
            type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=default_value if default_value is not None else spec.min_value,
            optional=optional,
            minValue=spec.min_value,
            maxValue=spec.max_value,
        )

    elif spec.input_type == InputType.BOOLEAN:
        return QgsProcessingParameterBoolean(
            name,
            description,
            defaultValue=default_value or False,
            optional=optional,
        )

    elif spec.input_type == InputType.CHOICE:
        return QgsProcessingParameterEnum(
            name,
            description,
            options=spec.choices,
            defaultValue=spec.choices.index(default_value) if default_value and default_value in spec.choices else 0,
            optional=optional,
        )

    elif spec.input_type == InputType.FILE_PATH:
        return QgsProcessingParameterFile(
            name,
            description,
            behavior=QgsProcessingParameterFile.Behavior.File,
            fileFilter=spec.file_filter,
            defaultValue=default_value or "",
            optional=optional,
        )

    elif spec.input_type == InputType.FOLDER_PATH:
        return QgsProcessingParameterFile(
            name,
            description,
            behavior=QgsProcessingParameterFile.Behavior.Folder,
            defaultValue=default_value or "",
            optional=optional,
        )

    elif spec.input_type == InputType.VECTOR_LAYER:
        return QgsProcessingParameterVectorLayer(
            name,
            description,
            optional=optional,
        )

    elif spec.input_type == InputType.RASTER_LAYER:
        return QgsProcessingParameterRasterLayer(
            name,
            description,
            optional=optional,
        )

    elif spec.input_type == InputType.ANY_LAYER:
        # Processing doesn't have a generic "any layer" - we'll use FeatureSource
        # which accepts both vector and raster
        from qgis.core import QgsProcessingParameterMapLayer
        return QgsProcessingParameterMapLayer(
            name,
            description,
            optional=optional,
        )

    elif spec.input_type == InputType.FIELD:
        # Field parameter needs a parent layer - use linked_layer_key
        return QgsProcessingParameterField(
            name,
            description,
            parentLayerParameterName=spec.linked_layer_key or "",
            optional=optional,
        )

    elif spec.input_type == InputType.CRS:
        return QgsProcessingParameterCrs(
            name,
            description,
            defaultValue=default_value or "EPSG:4326",
            optional=optional,
        )

    elif spec.input_type == InputType.TEXT_AREA:
        # Text area is just a multiline string in Processing
        return QgsProcessingParameterString(
            name,
            description,
            defaultValue=default_value or "",
            optional=optional,
            multiLine=True,
        )

    # Fallback to string for unknown types
    return QgsProcessingParameterString(
        name,
        description,
        defaultValue=str(default_value) if default_value else "",
        optional=optional,
    )


def extract_parameter_value(spec: InputSpec, parameters: dict, param_key: str, context, algorithm):
    """Extract and convert a parameter value from Processing parameters.

    Args:
        spec: Input specification from BaseApp
        parameters: Processing algorithm parameters dict
        param_key: Parameter key to extract
        context: QgsProcessingContext
        algorithm: QgsProcessingAlgorithm instance (for parameterAs* methods)

    Returns:
        Value in the format expected by BaseApp.execute_logic()
    """
    if spec.input_type in (InputType.STRING, InputType.TEXT_AREA):
        return algorithm.parameterAsString(parameters, param_key, context)

    elif spec.input_type == InputType.INTEGER:
        return algorithm.parameterAsInt(parameters, param_key, context)

    elif spec.input_type == InputType.FLOAT:
        return algorithm.parameterAsDouble(parameters, param_key, context)

    elif spec.input_type == InputType.BOOLEAN:
        return algorithm.parameterAsBool(parameters, param_key, context)

    elif spec.input_type == InputType.CHOICE:
        # Return the selected choice string
        enum_idx = algorithm.parameterAsEnum(parameters, param_key, context)
        if 0 <= enum_idx < len(spec.choices):
            return spec.choices[enum_idx]
        return spec.choices[0] if spec.choices else ""

    elif spec.input_type in (InputType.FILE_PATH, InputType.FOLDER_PATH):
        return algorithm.parameterAsFile(parameters, param_key, context)

    elif spec.input_type == InputType.VECTOR_LAYER:
        return algorithm.parameterAsVectorLayer(parameters, param_key, context)

    elif spec.input_type == InputType.RASTER_LAYER:
        return algorithm.parameterAsRasterLayer(parameters, param_key, context)

    elif spec.input_type == InputType.ANY_LAYER:
        return algorithm.parameterAsLayer(parameters, param_key, context)

    elif spec.input_type == InputType.FIELD:
        return algorithm.parameterAsString(parameters, param_key, context)

    elif spec.input_type == InputType.CRS:
        return algorithm.parameterAsCrs(parameters, param_key, context)

    # Fallback
    return parameters.get(param_key)
