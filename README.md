# Laptop Health Monitor — AI-Ready Edition

A professional, light-themed Windows desktop application for live laptop health monitoring, predictive maintenance, storage analysis, system inventory, reporting, and smart uninstallation.

## Works without the dataset

The application starts and operates immediately. Until a research model is trained, it uses a documented condition-based Remaining Useful Life estimate. It does **not** train or display results from fabricated synthetic data.

## Enable research AI later

1. Copy the NASA battery dataset into `ai/dataset/`.
2. Run `CHECK_DATASET.bat`.
3. Run `TRAIN_AI_MODEL.bat`.
4. Restart the application.

The training pipeline performs battery-group holdout validation and produces:

- MAE
- RMSE
- R²
- MAPE
- Accuracy
- Weighted precision
- Weighted recall
- Weighted F1-score
- Confusion matrix values
- Feature importance
- Test predictions

See `DATASET_SETUP_GUIDE.txt` for supported dataset layouts.

## First run

Extract the ZIP and double-click `RUN_LAPTOP_HEALTH_MONITOR.bat`. Use 64-bit Python 3.12 for the most reliable setup. Python 3.11 and 3.13 are also supported.

## Important research limitation

The NASA dataset models laboratory lithium-ion battery degradation. It supports battery-cycle RUL research; it does not establish a certified failure date for the complete laptop.
