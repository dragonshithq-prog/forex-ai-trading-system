# ML Models & Training

This directory contains machine learning model definitions, training scripts, and artifacts.

## Structure

```
ml/
├── models/           # Model architecture definitions
├── training/         # Training scripts and pipelines
├── notebooks/        # Jupyter notebooks for exploration
├── data/             # Training data (not committed to git)
├── artifacts/        # Trained model files (not committed to git)
└── config/           # Training configurations
```

## Models

- **Structure Agent**: LSTM-based market structure classifier
- **Trend Agent**: Transformer-based trend detection
- **Sentiment Agent**: FinBERT-based news sentiment analysis
- **Volatility Agent**: GARCH + Neural Network hybrid

## Training

```bash
# Train structure model
python -m ml.training.train_structure --data data/structure/ --epochs 100

# Optimize hyperparameters
python -m ml.training.optimize --model structure --trials 50
```

## Model Artifacts

Trained models are saved to `artifacts/` with versioning:
- `artifacts/structure/v1.0.0/model.pt`
- `artifacts/structure/v1.0.0/config.json`
- `artifacts/structure/v1.0.0/metrics.json`
