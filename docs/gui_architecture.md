# GUI Architecture

## Overview

The integrated GUI is now split into an app shell, global state/presenter layer, background job infrastructure, reusable components, and feature-specific tab controllers.

High-level flow:

1. `kbo_integrated_gui.py`
   - Thin entry point.
   - Delegates startup to `gui.app_shell.run()`.

2. `gui/app_shell.py`
   - Creates the DearPyGui context and viewport.
   - Builds global windows, tab registry, and the render loop.
   - Polls the shared `JobRunner`.
   - Applies debounced layout changes through `LayoutManager`.

3. `gui/state.py`
   - `AppStateModel`: pure application state.
   - `AppStatePresenter`: DearPyGui adapter for global status / alerts / error detail.
   - `AppState`: dispatcher/facade used by tabs.

4. `gui/jobs/*`
   - Shared background job execution.
   - Progress, logs, cancellation, result hand-off, and UI-thread polling.

5. `gui/components/*`
   - Reusable UI building blocks such as log panels, progress panels, file selectors, date picker, game selector, navigator panels, and warning tables.

6. `tabs/*`
   - Feature controllers only.
   - Tabs gather input, start shared jobs, and update feature-local views.
   - Heavy logic is delegated into `gui/*_service.py` or `gui/replay/*`.

## Module Map

### App shell and windows

- `gui/app_shell.py`
- `gui/layout_manager.py`
- `gui/windows/global_status_window.py`
- `gui/windows/global_alert_window.py`
- `gui/windows/db_detail_window.py`
- `gui/windows/alert_detail_window.py`

### State

- `gui/state.py`
- `tabs/shared_state.py`
  - Compatibility re-export for existing imports.

### Jobs

- `gui/jobs/task_state.py`
- `gui/jobs/job_runner.py`

### Reusable UI

- `gui/components/date_picker.py`
- `gui/components/file_selector.py`
- `gui/components/game_selector.py`
- `gui/components/log_panel.py`
- `gui/components/navigation.py`
- `gui/components/progress_panel.py`
- `gui/components/summary_card.py`
- `gui/components/warning_table.py`

### Collection

- `tabs/collection_tab.py`
- `gui/collection_service.py`

### Ingestion

- `tabs/ingestion_tab.py`
- `gui/ingestion_service.py`

### Replay

- `tabs/replay_tab.py`
- `gui/replay/models.py`
- `gui/replay/repository.py`
- `gui/replay/roster.py`
- `gui/replay/state_builder.py`
- `gui/replay/navigation.py`
- `gui/replay/anomaly.py`
- `gui/replay/renderers.py`

## Responsibility Moves

### `kbo_integrated_gui.py`

Before:
- Created every window.
- Owned layout logic.
- Owned the render loop.
- Owned global modal show/hide behavior.
- Instantiated tabs directly.

After:
- Only launches `gui.app_shell.run()`.

### `AppState`

Before:
- Stored data.
- Mutated DearPyGui widgets directly.
- Mixed notifications, status logs, error details, and DB indicator updates.

After:
- `AppStateModel` stores state only.
- `AppStatePresenter` updates DearPyGui widgets.
- `AppState` dispatches changes and notifies subscribers such as tabs.

### `CollectionTab`

Before:
- UI, date picker, worker thread, queue pump, scraping, validation, and log mutation lived in one class.

After:
- `CollectionTab` handles form input, shared job lifecycle, and result rendering.
- `CollectionService` owns collection execution and structured result creation.
- `DatePicker` is reusable.

### `IngestionTab`

Before:
- Directly ran schema creation and JSON loading inline on the UI thread.

After:
- `IngestionTab` launches shared jobs for manifest/schema/load/validate/sample-loop flows.
- `IngestionService` contains background task logic.
- `DatabaseService` isolates DB connection and game list queries.

### `ReplayTab`

Before:
- SQL, tuple indexing, derived state, anomaly detection, navigation, and drawing were all embedded in one class.

After:
- `ReplayRepository` owns SQL and typed row creation.
- `ReplayStateBuilder` owns replay-derived state.
- `ReplayNavigationModelBuilder` owns event/pitch/PA/inning navigation models.
- `ReplayAnomalyDetector` owns reusable warning detection.
- `FieldOverlayRenderer` and `StrikeZoneRenderer` own drawing.
- `ReplayTab` is now a view/controller.

## Adding a New Tab

1. Create a feature controller under `tabs/`.
2. Move heavy logic into `gui/<feature>_service.py` or a `gui/<feature>/` package.
3. Use `TagNamespace` for component-local tags.
4. Use the shared `JobRunner` for long-running work.
5. Register the tab in `gui/tabs/registry.py`.

## Layout Strategy

The old GUI reapplied layout every frame. The new shell uses:

- `LayoutManager.mark_dirty()` on resize or when a tab changes visible sub-sections.
- A debounced `poll()` in the render loop.
- Per-tab `apply_responsive_layout(content_w, content_h)` hooks.

This keeps the render loop alive for DearPyGui and background job delivery, but removes unconditional full-layout recalculation on every frame.

## Test Strategy

Pure logic is now testable without opening the GUI:

- `tests/test_gui_job_runner.py`
- `tests/test_gui_layout_manager.py`
- `tests/test_replay_refactor.py`

Existing editor and ingestion-related tests continue to run against the refactored code paths.
