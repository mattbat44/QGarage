# QGarage Changelog

## [2.1.3] - 2026-06-26

### Fixed
- Sanitize inherited QGIS Python environment variables before verifying `uv`
- Verify `uv --version` without a console window on Windows for consistency with other bridge subprocesses
- Convert uv verification timeouts and subprocess failures into plugin-level availability errors instead of crashing plugin startup

## [2.1.0] - 2026-06-20

### Added
- Persistent per-app environments (uv/pixi) with improved lifecycle handling
- Robust unloading/reload/upgrade paths for the plugin
- Strengthened app install/update flows including side-by-side test packaging
- Per-app bridge resolution improved to avoid cross-package namespace issues
- Test-packaging flow to support safe side-by-side testing without clobbering the official repository plugin

### Fixed
- Windows uv subprocess launch quoting issues
- SSL_CERT_DIR sanitization for subprocess environments
- Environment lifecycle management on Windows platforms
- App upgrade/reinstall cleanup improvements

### Changed
- Enhanced bridge resolution logic for better uv/pixi backend selection
- Improved error reporting during environment setup
- Strengthened subprocess isolation and cleanup

### Backwards Compatibility
- Maintains existing app APIs
- Minor internal changes designed to be non-breaking for end users

## [2.0.1] - 2026-06-19

### Fixed
- Fix Windows uv subprocess launch quoting and SSL_CERT_DIR sanitization

## [2.0.0] - 2026-06-15

### Added
- Dual uv/pixi backends for app environments
- Asynchronous environment preparation during installs
- Processing Toolbox integration for declarative apps
- Richer scaffolding with backend selection and custom destinations
- Bundled TestToolbox examples for both uv and pixi workflows

### Changed
- Major version upgrade with new architecture
- Improved setup error reporting
