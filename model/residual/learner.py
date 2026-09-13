"""Deterministic, site-balanced TabM regression for process-model residuals.

PyTorch and the TabM packages are imported only when fitting, predicting, or
loading a checkpoint, so importing the process-model package remains optional-
dependency free.
"""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


_CHECKPOINT_FORMAT = "grape-growth-stage-tabm-residual"
_CHECKPOINT_VERSION = 1


def _positive_integer(value: int, name: str, *, minimum: int = 1) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class TabMConfig:
    """Hyperparameters for the bounded CPU TabM learner."""

    n_blocks: int = 2
    d_block: int = 128
    k: int = 16
    dropout: float = 0.1
    n_bins: int = 16
    d_embedding: int = 16
    lr: float = 0.002
    weight_decay: float = 0.0003
    batch_size: int = 256
    max_epochs: int = 300
    patience: int = 30
    threads: int = 2

    def __post_init__(self) -> None:
        for name in ("n_blocks", "d_block", "k", "d_embedding", "batch_size",
                     "max_epochs", "patience", "threads"):
            _positive_integer(getattr(self, name), name)
        _positive_integer(self.n_bins, "n_bins", minimum=2)
        if not isinstance(self.dropout, (int, float)) or isinstance(self.dropout, bool):
            raise ValueError("dropout must be numeric")
        if not 0.0 <= float(self.dropout) < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if (not isinstance(self.lr, (int, float)) or isinstance(self.lr, bool)
                or not np.isfinite(self.lr) or self.lr <= 0):
            raise ValueError("lr must be finite and positive")
        if (not isinstance(self.weight_decay, (int, float))
                or isinstance(self.weight_decay, bool)
                or not np.isfinite(self.weight_decay) or self.weight_decay < 0):
            raise ValueError("weight_decay must be finite and non-negative")


def _validate_frame(x: pd.DataFrame, *, allow_empty: bool) -> np.ndarray:
    if not isinstance(x, pd.DataFrame):
        raise TypeError("x must be a pandas DataFrame")
    if not allow_empty and len(x) < 2:
        raise ValueError("x must contain at least two rows")
    if x.shape[1] == 0:
        raise ValueError("x must contain at least one feature")
    if not x.columns.is_unique or not all(isinstance(column, str) for column in x.columns):
        raise ValueError("x requires unique string column names")
    invalid_dtype = any(
        pd.api.types.is_bool_dtype(dtype)
        or pd.api.types.is_complex_dtype(dtype)
        or not pd.api.types.is_numeric_dtype(dtype)
        for dtype in x.dtypes
    )
    if invalid_dtype:
        raise TypeError("x must contain only real numeric, non-boolean columns")
    try:
        values = x.to_numpy(dtype=np.float64, na_value=np.nan)
    except (TypeError, ValueError) as error:
        raise TypeError("x must be convertible to numeric floating-point values") from error
    if np.isinf(values).any():
        raise ValueError("x must not contain infinite values")
    return values


@dataclass(frozen=True)
class _Preprocessor:
    columns: tuple[str, ...]
    usable_columns: tuple[str, ...]
    usable_indices: tuple[int, ...]
    medians: tuple[float, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]

    @classmethod
    def fit(cls, x: pd.DataFrame) -> "_Preprocessor":
        values = _validate_frame(x, allow_empty=False)
        usable_indices: list[int] = []
        medians: list[float] = []
        means: list[float] = []
        scales: list[float] = []
        for index in range(values.shape[1]):
            column = values[:, index]
            finite = column[~np.isnan(column)]
            if finite.size == 0:
                continue
            median = float(np.median(finite))
            imputed = np.where(np.isnan(column), median, column)
            if np.ptp(imputed) == 0.0:
                continue
            scale = float(np.std(imputed, ddof=0))
            if not np.isfinite(scale) or scale <= 0.0:
                continue
            usable_indices.append(index)
            medians.append(median)
            means.append(float(np.mean(imputed)))
            scales.append(scale)
        if not usable_indices:
            raise ValueError("x has no usable non-constant numeric features")
        columns = tuple(x.columns)
        return cls(
            columns=columns,
            usable_columns=tuple(columns[index] for index in usable_indices),
            usable_indices=tuple(usable_indices),
            medians=tuple(medians),
            means=tuple(means),
            scales=tuple(scales),
        )

    def transform(self, x: pd.DataFrame) -> np.ndarray:
        values = _validate_frame(x, allow_empty=True)
        if tuple(x.columns) != self.columns:
            raise ValueError(
                "Feature schema mismatch: columns and ordering must match training data"
            )
        selected = values[:, self.usable_indices]
        medians = np.asarray(self.medians, dtype=np.float64)
        selected = np.where(np.isnan(selected), medians, selected)
        transformed = (
            selected - np.asarray(self.means, dtype=np.float64)
        ) / np.asarray(self.scales, dtype=np.float64)
        if not np.isfinite(transformed).all():
            raise ValueError("Preprocessed features must be finite")
        return np.asarray(transformed, dtype=np.float32)

    def checkpoint(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "usable_columns": list(self.usable_columns),
            "usable_indices": list(self.usable_indices),
            "medians": list(self.medians),
            "means": list(self.means),
            "scales": list(self.scales),
        }

    @classmethod
    def from_checkpoint(cls, state: dict[str, Any]) -> "_Preprocessor":
        try:
            result = cls(
                columns=tuple(state["columns"]),
                usable_columns=tuple(state["usable_columns"]),
                usable_indices=tuple(int(value) for value in state["usable_indices"]),
                medians=tuple(float(value) for value in state["medians"]),
                means=tuple(float(value) for value in state["means"]),
                scales=tuple(float(value) for value in state["scales"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid checkpoint preprocessing state") from error
        size = len(result.usable_indices)
        if (not result.columns or not all(isinstance(column, str) for column in result.columns)
                or len(set(result.columns)) != len(result.columns)
                or size == 0
                or any(len(values) != size for values in (
                    result.usable_columns, result.medians, result.means, result.scales))
                or any(index < 0 or index >= len(result.columns)
                       for index in result.usable_indices)
                or tuple(result.columns[index] for index in result.usable_indices)
                       != result.usable_columns
                or not np.isfinite(np.asarray(
                    [*result.medians, *result.means, *result.scales], dtype=float
                )).all()
                or any(scale <= 0 for scale in result.scales)):
            raise ValueError("Invalid checkpoint preprocessing state")
        return result


def _optional_stack():
    try:
        import torch
        import tabm
        import rtdl_num_embeddings
    except ModuleNotFoundError as error:
        raise ImportError(
            "The TabM residual learner requires torch, tabm, and "
            "rtdl_num_embeddings"
        ) from error
    return torch, tabm, rtdl_num_embeddings


def _site_weights(sites) -> np.ndarray:
    values = np.asarray(sites)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("sites must be a non-empty one-dimensional array")
    if not all(isinstance(value, (str, np.str_)) for value in values.tolist()):
        raise TypeError("sites must contain strings")
    _, inverse, counts = np.unique(values.astype(str), return_inverse=True, return_counts=True)
    weights = 1.0 / counts[inverse].astype(np.float64)
    return weights / weights.mean()


def _weighted_member_mse(predictions, target, global_weights):
    """Mean member MSE per row, weighted by globally normalized site weights."""
    if predictions.ndim == 3 and predictions.shape[-1] == 1:
        predictions = predictions.squeeze(-1)
    if predictions.ndim != 2:
        raise ValueError("TabM predictions must have shape (rows, members[, 1])")
    if target.ndim != 1 or global_weights.ndim != 1:
        raise ValueError("target and weights must be one-dimensional")
    if len(predictions) != len(target) or len(target) != len(global_weights):
        raise ValueError("Prediction, target, and weight lengths must match")
    row_losses = (predictions - target[:, None]).square().mean(dim=1)
    return (row_losses * global_weights).mean()


def _make_model(config: TabMConfig, bins: tuple[tuple[float, ...], ...]):
    torch, tabm, rtdl_num_embeddings = _optional_stack()
    bin_tensors = [torch.tensor(edges, dtype=torch.float32) for edges in bins]
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"The .* feature has just two bin edges.*",
            category=UserWarning,
        )
        embeddings = rtdl_num_embeddings.PiecewiseLinearEmbeddings(
            bin_tensors,
            config.d_embedding,
            activation=False,
            version="B",
        )
    return tabm.TabM.make(
        n_num_features=len(bins),
        cat_cardinalities=[],
        d_out=1,
        num_embeddings=embeddings,
        n_blocks=config.n_blocks,
        d_block=config.d_block,
        dropout=float(config.dropout),
        k=config.k,
    )


def _predict_in_batches(model, values, batch_size):
    """Keep only ensemble-mean row outputs; callers set eval/inference mode.

    Concatenation preserves row order and permits the original single global
    validation reduction, including its globally normalized site weights.
    """
    torch, _, _ = _optional_stack()
    return torch.cat([
        model(batch).squeeze(-1).mean(dim=1)
        for batch in values.split(batch_size)
    ])


class TabMPredictor:
    """Fitted preprocessing and official TabM model for residual-day inference."""

    model_class = "tabm.TabM"

    def __init__(
        self,
        *,
        model,
        config: TabMConfig,
        preprocessor: _Preprocessor,
        bins: tuple[tuple[float, ...], ...],
        target_mean: float,
        target_scale: float,
    ) -> None:
        self._model = model
        self.config = config
        self.preprocessor = preprocessor
        self.bins = bins
        self.target_mean = float(target_mean)
        self.target_scale = float(target_scale)

    @property
    def columns(self) -> tuple[str, ...]:
        return self.preprocessor.columns

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        torch, _, _ = _optional_stack()
        values = self.preprocessor.transform(x)
        if len(values) == 0:
            return np.empty(0, dtype=np.float64)
        self._model.eval()
        with torch.inference_mode():
            prediction = _predict_in_batches(
                self._model, torch.from_numpy(values), self.config.batch_size
            ).cpu().numpy().astype(np.float64)
        return prediction * self.target_scale + self.target_mean

    def save(self, path) -> None:
        """Exclusive-create a weights-only-loadable, self-contained checkpoint."""
        torch, _, _ = _optional_stack()
        checkpoint = {
            "format": _CHECKPOINT_FORMAT,
            "version": _CHECKPOINT_VERSION,
            "config": asdict(self.config),
            "preprocessor": self.preprocessor.checkpoint(),
            "bins": [list(edges) for edges in self.bins],
            "target_mean": self.target_mean,
            "target_scale": self.target_scale,
            "model_state": {
                name: value.detach().cpu() for name, value in self._model.state_dict().items()
            },
        }
        with Path(path).open("xb") as file:
            torch.save(checkpoint, file)


@dataclass(frozen=True)
class LearnerResult:
    predictor: TabMPredictor
    best_epoch: int
    history: list[dict[str, float | int]]


def _supervised_arrays(x, y, sites, *, label: str):
    if not isinstance(y, np.ndarray):
        raise TypeError(f"{label} y must be a numpy array")
    if y.ndim != 1:
        raise ValueError(f"{label} y must be one-dimensional")
    try:
        target = y.astype(np.float64, copy=False)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{label} y must be numeric") from error
    if not np.isfinite(target).all():
        raise ValueError(f"{label} y must contain only finite values")
    site_values = np.asarray(sites)
    if site_values.ndim != 1:
        raise ValueError(f"{label} sites must be one-dimensional")
    if len(x) != len(target) or len(target) != len(site_values):
        raise ValueError(f"{label} x, y, and sites must have matching length")
    weights = _site_weights(site_values)
    return target, site_values.astype(str), weights


def _clone_state(model) -> dict[str, Any]:
    return {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}


def fit_learner(
    x,
    y,
    sites,
    *,
    seed,
    config,
    validation=None,
    epochs=None,
) -> LearnerResult:
    """Fit with either validation early stopping or a fixed final epoch count."""
    if (validation is None) == (epochs is None):
        raise ValueError("Require exactly one of validation or epochs")
    if not isinstance(config, TabMConfig):
        raise TypeError("config must be a TabMConfig")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if epochs is not None:
        _positive_integer(epochs, "epochs")

    preprocessor = _Preprocessor.fit(x)
    target, train_sites, train_weights = _supervised_arrays(x, y, sites, label="Training")
    train_x = preprocessor.transform(x)
    validation_arrays = None
    if validation is not None:
        if not isinstance(validation, tuple) or len(validation) != 3:
            raise TypeError("validation must be an (x, y, sites) tuple")
        valid_x_frame, valid_y_input, valid_sites_input = validation
        valid_target, valid_sites, valid_weights = _supervised_arrays(
            valid_x_frame, valid_y_input, valid_sites_input, label="Validation"
        )
        overlap = set(train_sites).intersection(valid_sites)
        if overlap:
            raise ValueError("Training and validation sites overlap")
        valid_x = preprocessor.transform(valid_x_frame)
        validation_arrays = valid_x, valid_target, valid_weights

    target_mean = float(target.mean())
    target_scale = float(target.std(ddof=0))
    if target_scale == 0.0:
        target_scale = 1.0
    standardized_target = (target - target_mean) / target_scale

    torch, _, rtdl_num_embeddings = _optional_stack()
    torch.manual_seed(int(seed))
    old_threads = torch.get_num_threads()
    old_deterministic = torch.are_deterministic_algorithms_enabled()
    torch.set_num_threads(config.threads)
    torch.use_deterministic_algorithms(True)
    try:
        train_tensor = torch.from_numpy(train_x)
        bin_count = min(config.n_bins, len(train_x) - 1)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"The .* feature has just two bin edges.*",
                category=UserWarning,
            )
            bins_tensor = rtdl_num_embeddings.compute_bins(
                train_tensor, n_bins=bin_count
            )
        bins = tuple(tuple(float(value) for value in edges.tolist()) for edges in bins_tensor)
        model = _make_model(config, bins)
        optimizer = torch.optim.AdamW(
            model.parameters(), lr=float(config.lr), weight_decay=float(config.weight_decay)
        )
        target_tensor = torch.tensor(standardized_target, dtype=torch.float32)
        weight_tensor = torch.tensor(train_weights, dtype=torch.float32)
        if validation_arrays is not None:
            valid_x, valid_target, valid_weights = validation_arrays
            valid_tensor = torch.from_numpy(valid_x)
            valid_target_tensor = torch.tensor(valid_target, dtype=torch.float32)
            valid_weight_tensor = torch.tensor(valid_weights, dtype=torch.float32)
            epoch_limit = config.max_epochs
        else:
            epoch_limit = int(epochs)

        history: list[dict[str, float | int]] = []
        best_epoch = 0
        best_metric = np.inf
        best_state = None
        non_improving = 0
        generator = torch.Generator(device="cpu")
        generator.manual_seed(int(seed))
        for epoch_index in range(epoch_limit):
            model.train()
            permutation = torch.randperm(len(train_tensor), generator=generator)
            loss_sum = 0.0
            for indices in permutation.split(config.batch_size):
                optimizer.zero_grad(set_to_none=True)
                predictions = model(train_tensor[indices])
                loss = _weighted_member_mse(
                    predictions, target_tensor[indices], weight_tensor[indices]
                )
                loss.backward()
                optimizer.step()
                loss_sum += float(loss.detach()) * len(indices)
            record: dict[str, float | int] = {
                "epoch": epoch_index + 1,
                "train_loss": loss_sum / len(train_tensor),
            }

            if validation_arrays is not None:
                model.eval()
                with torch.inference_mode():
                    valid_prediction = _predict_in_batches(model, valid_tensor, config.batch_size)
                    valid_prediction = valid_prediction * target_scale + target_mean
                    validation_mae = float(
                        ((valid_prediction - valid_target_tensor).abs()
                         * valid_weight_tensor).mean()
                    )
                record["validation_mae"] = validation_mae
                if validation_mae < best_metric:
                    best_metric = validation_mae
                    best_epoch = epoch_index + 1
                    best_state = _clone_state(model)
                    non_improving = 0
                else:
                    non_improving += 1
                history.append(record)
                if non_improving >= config.patience:
                    break
            else:
                history.append(record)

        if validation_arrays is not None:
            if best_state is None:
                raise RuntimeError("Validation training did not produce a finite score")
            model.load_state_dict(best_state, strict=True)
        else:
            best_epoch = epoch_limit
        model.eval()
    finally:
        torch.use_deterministic_algorithms(old_deterministic)
        torch.set_num_threads(old_threads)

    predictor = TabMPredictor(
        model=model,
        config=config,
        preprocessor=preprocessor,
        bins=bins,
        target_mean=target_mean,
        target_scale=target_scale,
    )
    return LearnerResult(predictor=predictor, best_epoch=best_epoch, history=history)


def load_predictor(path) -> TabMPredictor:
    """Load a trusted local checkpoint with PyTorch's restricted loader."""
    torch, _, _ = _optional_stack()
    try:
        checkpoint = torch.load(Path(path), map_location="cpu", weights_only=True)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise ValueError("Could not load a valid TabM residual checkpoint") from error
    if (not isinstance(checkpoint, dict)
            or checkpoint.get("format") != _CHECKPOINT_FORMAT
            or checkpoint.get("version") != _CHECKPOINT_VERSION):
        raise ValueError("Unsupported TabM residual checkpoint format")
    try:
        config = TabMConfig(**checkpoint["config"])
        preprocessor = _Preprocessor.from_checkpoint(checkpoint["preprocessor"])
        bins = tuple(
            tuple(float(value) for value in edges) for edges in checkpoint["bins"]
        )
        target_mean = float(checkpoint["target_mean"])
        target_scale = float(checkpoint["target_scale"])
        model_state = checkpoint["model_state"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid TabM residual checkpoint contents") from error
    if (len(bins) != len(preprocessor.usable_columns)
            or any(len(edges) < 2 or not np.isfinite(edges).all()
                   or any(right <= left for left, right in zip(edges, edges[1:]))
                   for edges in bins)
            or not np.isfinite([target_mean, target_scale]).all()
            or target_scale <= 0):
        raise ValueError("Invalid TabM residual checkpoint contents")
    model = _make_model(config, bins)
    try:
        model.load_state_dict(model_state, strict=True)
    except (RuntimeError, TypeError) as error:
        raise ValueError("Checkpoint model weights do not match its schema") from error
    model.eval()
    return TabMPredictor(
        model=model,
        config=config,
        preprocessor=preprocessor,
        bins=bins,
        target_mean=target_mean,
        target_scale=target_scale,
    )


__all__ = ["LearnerResult", "TabMConfig", "TabMPredictor", "fit_learner", "load_predictor"]
