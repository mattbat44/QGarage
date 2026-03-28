# Toolbox Functionality

QGarage now supports importing and managing **toolboxes** - collections of multiple related apps grouped together. This feature allows you to organize and distribute multiple apps as a single package.

## What is a Toolbox?

A toolbox is a container that holds multiple apps. When you import a toolbox, all apps inside it are displayed together in the QGarage dashboard under an expandable/collapsible section.

### Toolbox Structure

A toolbox has the following directory structure:

```
my_toolbox/
├── toolbox_meta.json       # Toolbox metadata file
├── app1/
│   ├── app_meta.json       # First app metadata
│   ├── main.py            # First app code
│   └── requirements.txt   # (optional) First app dependencies
├── app2/
│   ├── app_meta.json      # Second app metadata
│   ├── main.py           # Second app code
│   └── requirements.txt  # (optional) Second app dependencies
└── app3/
    ├── app_meta.json     # Third app metadata
    ├── main.py          # Third app code
    └── requirements.txt # (optional) Third app dependencies
```

## Toolbox Metadata Format

The `toolbox_meta.json` file defines the toolbox properties:

```json
{
  "name": "My Awesome Toolbox",
  "id": "my_awesome_toolbox",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "A collection of useful GIS tools",
  "icon_path": "icon.png",
  "tags": ["geoprocessing", "analysis"]
}
```

### Required Fields
- `id`: Unique identifier for the toolbox (lowercase, underscores allowed)
- `name`: Display name for the toolbox

### Optional Fields
- `version`: Version number
- `author`: Author name
- `description`: Brief description of the toolbox
- `icon_path`: Path to an icon file (relative to toolbox directory)
- `tags`: Array of tags for searchability

## Creating a Toolbox

1. **Create the toolbox directory**:
   ```bash
   mkdir my_toolbox
   ```

2. **Create the `toolbox_meta.json` file**:
   ```json
   {
     "name": "My Toolbox",
     "id": "my_toolbox",
     "description": "A collection of related tools"
   }
   ```

3. **Add apps to the toolbox**:
   - Each app should be in its own subdirectory
   - Each app must have an `app_meta.json` file
   - Each app must have a `main.py` file with a BaseApp subclass

4. **Package as ZIP** (optional):
   ```bash
   zip -r my_toolbox.zip my_toolbox/
   ```

## Installing a Toolbox

### From ZIP File (Remote URL)
1. Click the "+ Install" button in the QGarage dashboard
2. Enter the URL to your toolbox ZIP file
3. Click "Install from URL"
4. The toolbox and all its apps will be installed

### From Local Folder
1. Click the "+ Install" button in the QGarage dashboard
2. Click "Browse Local Folder"
3. Select the toolbox directory
4. Click "Install from Folder"
5. The toolbox and all its apps will be installed

## Using a Toolbox in the Dashboard

Once installed, toolboxes appear in the QGarage dashboard:

1. **Toolbox Card**: Displays the toolbox name, description, and app count
2. **Expand/Collapse**: Click the arrow button or the toolbox header to show/hide apps
3. **App Cards**: When expanded, shows all apps contained in the toolbox
4. **Running Apps**: Click "Open" on any app card to run it
5. **Search**: Searching filters toolboxes by toolbox name, description, or any contained app

### Visual Features
- Toolboxes have a distinct orange icon (vs. green for standalone apps)
- App count badge shows how many apps are in the toolbox
- Expandable/collapsible sections to manage screen space
- Apps within toolboxes can be run independently

## Example: Sample Toolbox

QGarage includes a sample toolbox for demonstration:

**Location**: `qgarage/apps/sample_toolbox/`

**Contains**:
1. **Buffer Tool** - Creates buffers around vector features
2. **Merge Tool** - Merges multiple vector layers

**To see it in action**:
1. Install QGarage
2. Open the QGarage dashboard
3. Look for "Sample Toolbox" in the app list
4. Click to expand and see the Buffer Tool and Merge Tool

## App Discovery and Loading

- **Discovery**: When QGarage starts, it scans the `apps/` directory for both:
  - Standalone apps (directories with `app_meta.json`)
  - Toolboxes (directories with `toolbox_meta.json`)
- **Loading**: Apps within toolboxes are loaded lazily when you open them
- **Registry**: Toolboxes are tracked separately from apps, but apps know their parent toolbox

## Differences from Standalone Apps

| Feature | Standalone App | App in Toolbox |
|---------|---------------|----------------|
| Installation | Individual ZIP or folder | Part of toolbox package |
| Dashboard Display | Standalone card | Inside expandable toolbox card |
| Metadata File | `app_meta.json` only | `app_meta.json` + parent `toolbox_meta.json` |
| Dependencies | Per-app `.venv` | Per-app `.venv` (independent) |
| Removal | Remove individual app | Remove entire toolbox or individual apps |

## Best Practices

1. **Grouping**: Group related apps into toolboxes
   - Example: "Hydrology Toolbox" with flow direction, watershed, etc.

2. **Naming**: Use clear, descriptive names for both toolbox and apps
   - Good: "Raster Analysis Toolbox" → "Slope Calculator", "Aspect Calculator"
   - Avoid: "Tools" → "Tool1", "Tool2"

3. **Dependencies**: Each app can have its own `requirements.txt`
   - Apps in the same toolbox can have different dependencies
   - Each app gets its own isolated virtual environment

4. **Documentation**: Include a README in your toolbox ZIP
   - Explain what each app does
   - Provide usage examples
   - List any prerequisites

5. **Versioning**: Version both the toolbox and individual apps
   - Toolbox version for the overall package
   - App versions for individual tools

## Technical Details

### Registry Structure
- `AppRegistry._entries`: Dictionary of all apps (both standalone and in toolboxes)
- `AppRegistry._toolbox_entries`: Dictionary of all toolboxes
- `AppEntry.parent_toolbox_id`: Links apps to their parent toolbox (None for standalone apps)
- `ToolboxEntry.app_entries`: Dictionary of apps within a toolbox

### UI Components
- `ToolboxCardWidget`: Custom widget for displaying toolboxes
  - Header with toolbox info and expand/collapse button
  - Container for app cards (shown when expanded)
  - Forwards app run/reset signals to dashboard
- `AppCardWidget`: Reused for both standalone apps and apps in toolboxes

### Install Workers
- `DownloadAndInstallWorker`: Handles ZIP downloads from URLs
  - Checks for `toolbox_meta.json` first, then `app_meta.json`
  - Installs entire toolbox structure or single app
- `LocalInstallWorker`: Handles local folder installations
  - Same logic as download worker but for local paths

## Troubleshooting

**Toolbox not appearing after install**:
- Check that `toolbox_meta.json` has a valid `id` field
- Ensure apps within have valid `app_meta.json` files
- Check QGarage logs for errors

**Apps in toolbox not running**:
- Each app needs a valid `main.py` with BaseApp subclass
- Check app-specific logs for errors
- Try clicking "Reset" on a failed app

**Search not finding toolbox**:
- Search looks at toolbox name, description, tags, AND app names/descriptions
- Try broader search terms

## Future Enhancements

Potential improvements for toolbox functionality:
- Toolbox-level dependencies shared across all apps
- Batch operations on all apps in a toolbox
- Toolbox templates for common workflows
- Export toolbox with all apps to ZIP
- Toolbox marketplace/catalog
