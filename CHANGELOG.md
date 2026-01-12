# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Google Photos Library API integration with OAuth 2.0 authentication
- Google Photos API client using `requests` library for REST API calls
- Google Photos viewer widget with tabbed interface for:
  - Media items table with metadata display
  - Albums table
  - Shared albums table
  - Detailed JSON view for selected items
- Qt Designer UI file (`google_photos_view.ui`) for customizable GUI layout
- Comprehensive API reference documentation (`API_REFERENCE.md`)
- GitHub Pages website with modern, responsive design
- Privacy Policy page (GDPR and CCPA compliant)
- Terms of Service page (US and EU compliant)
- Troubleshooting guide (`TROUBLESHOOTING.md`) for common issues
- Credentials file example (`credentials.json.example`)
- Image assets for README and website
- Support for automatic OAuth token refresh
- Error handling with detailed 403 error messages
- Documentation for authentication setup in README

### Changed
- Updated OAuth scope from deprecated `photoslibrary.readonly` to `photoslibrary.readonly.appcreateddata`
- Enhanced error messages for 403 Forbidden errors with troubleshooting guidance
- Updated documentation dates to 2026
- Improved README with comprehensive setup instructions and troubleshooting section

### Fixed
- Corrected OAuth scope to use current API-compliant scope (`photoslibrary.readonly.appcreateddata`)
- Updated all references to deprecated scope in code and documentation### Documentation
- Added complete API reference documentation covering all endpoints and data structures
- Added detailed authentication setup instructions
- Added troubleshooting guide for common issues (403 errors, authentication problems)
- Added Privacy Policy and Terms of Service pages
- Enhanced README with features, usage, and project structure documentation
- Added GitHub Pages website documentation