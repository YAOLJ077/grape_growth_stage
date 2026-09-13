"""Behavioral tests for the optional, site-balanced TabM residual learner."""

from dataclasses import FrozenInstanceError
import importlib
import warnings

import numpy as np
import pandas as pd
import pytest


def learner():
    return importlib.import_module("model.residual.learner")


def tiny_config(**overrides):
    values = dict(
        n_blocks=1,
        d_block=12,
        k=2,
        dropout=0.0,
        n_bins=4,
        d_embedding=4,
        lr=0.01,
        weight_decay=0.0,
        batch_size=8,
        max_epochs=8,
        patience=2,
        threads=1,
    )
    values.update(overrides)
    return learner().TabMConfig(**values)


def regression_data(n=32, *, prefix="train"):
    z = np.linspace(-2.0, 2.0, n, dtype=np.float64)
    x = pd.DataFrame({"heat": z, "water": np.sin(z)})
    y = (2.5 * z - 0.75 * np.sin(z) + 4.0).astype(np.float64)
    sites = np.asarray([f"{prefix}-{i // 2}" for i in range(n)], dtype=str)
    return x, y, sites


def test_config_is_frozen_and_rejects_invalid_hyperparameters():
    config = learner().TabMConfig()
    assert config.n_blocks == 2
    assert config.d_block == 128
    assert config.k == 16
    assert config.n_bins == 16
    assert config.d_embedding == 16
    with pytest.raises(FrozenInstanceError):
        config.k = 3

    invalid = [
        {"n_blocks": 0},
        {"d_block": 0},
        {"k": 0},
        {"dropout": -0.01},
        {"dropout": 1.0},
        {"n_bins": 1},
        {"d_embedding": 0},
        {"lr": 0.0},
        {"weight_decay": -0.1},
        {"batch_size": 0},
        {"max_epochs": 0},
        {"patience": 0},
        {"threads": 0},
    ]
    for override in invalid:
        with pytest.raises(ValueError):
            learner().TabMConfig(**override)


def test_site_weights_are_inverse_counts_with_global_mean_one():
    weights = learner()._site_weights(np.asarray(["A", "A", "B", "C", "C", "C"]))
    np.testing.assert_allclose(weights, [1.0, 1.0, 2.0, 2.0 / 3.0, 2.0 / 3.0, 2.0 / 3.0])
    assert weights.mean() == pytest.approx(1.0)


def test_weighted_loss_averages_member_errors_before_weighting_rows():
    torch = pytest.importorskip("torch")
    predictions = torch.tensor([[1.0, 3.0], [4.0, 6.0]])
    target = torch.tensor([2.0, 3.0])
    global_weights = torch.tensor([0.5, 1.5])

    loss = learner()._weighted_member_mse(predictions, target, global_weights)

    # Row MSEs are 1 and 5; their globally weighted arithmetic mean is 4.
    assert loss.item() == pytest.approx(4.0)


def test_preprocessing_is_fit_on_training_and_drops_constant_columns():
    train = pd.DataFrame(
        {
            "varying": [0.0, 2.0, np.nan, 6.0],
            "constant": [9.0, 9.0, np.nan, 9.0],
            "all_missing": [np.nan, np.nan, np.nan, np.nan],
        }
    )
    valid = pd.DataFrame(
        {
            "varying": [1000.0, np.nan],
            "constant": [-1000.0, 12.0],
            "all_missing": [1.0, 2.0],
        }
    )

    preprocessor = learner()._Preprocessor.fit(train)
    transformed = preprocessor.transform(valid)

    assert preprocessor.columns == ("varying", "constant", "all_missing")
    assert preprocessor.usable_columns == ("varying",)
    assert preprocessor.medians == pytest.approx((2.0,))
    # Validation extremes and values in discarded columns cannot affect training stats.
    assert preprocessor.means == pytest.approx((2.5,))
    assert preprocessor.scales == pytest.approx((np.sqrt(4.75),))
    assert transformed.shape == (2, 1)
    assert transformed[1, 0] == pytest.approx((2.0 - 2.5) / np.sqrt(4.75))


def test_validation_early_stops_a_real_tabm_and_uses_train_target_statistics():
    tabm = pytest.importorskip("tabm")
    pytest.importorskip("rtdl_num_embeddings")
    x, y, sites = regression_data(32)
    xv, yv, sv = regression_data(16, prefix="valid")
    yv = yv + 10_000.0
    config = tiny_config(lr=1e-12, max_epochs=8, patience=2)

    result = learner().fit_learner(
        x,
        y,
        sites,
        seed=17,
        config=config,
        validation=(xv, yv, sv),
    )

    assert isinstance(result.predictor._model, tabm.TabM)
    assert result.predictor.model_class == "tabm.TabM"
    assert result.predictor.target_mean == pytest.approx(float(y.mean()))
    assert result.predictor.target_scale == pytest.approx(float(y.std(ddof=0)))
    transformed_train = result.predictor.preprocessor.transform(x)
    for index, edges in enumerate(result.predictor.bins):
        assert edges[0] == pytest.approx(float(transformed_train[:, index].min()))
        assert edges[-1] == pytest.approx(float(transformed_train[:, index].max()))
    assert 1 <= result.best_epoch < config.max_epochs
    assert len(result.history) == result.best_epoch + config.patience
    assert result.history[result.best_epoch - 1]["validation_mae"] == pytest.approx(
        min(row["validation_mae"] for row in result.history)
    )


def test_fixed_epoch_training_is_repeatable_for_the_same_seed():
    pytest.importorskip("tabm")
    x, y, sites = regression_data(32)
    config = tiny_config()

    first = learner().fit_learner(x, y, sites, seed=23, config=config, epochs=3)
    second = learner().fit_learner(x, y, sites, seed=23, config=config, epochs=3)

    assert first.best_epoch == second.best_epoch == 3
    np.testing.assert_array_equal(first.predictor.predict(x), second.predictor.predict(x))
    assert first.history == second.history


def test_binary_numeric_features_do_not_emit_a_dependency_warning():
    pytest.importorskip("tabm")
    x, y, sites = regression_data(20)
    x["binary"] = [0.0] * 19 + [1.0]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        learner().fit_learner(x, y, sites, seed=29, config=tiny_config(), epochs=1)

    assert not [item for item in caught if "two bin edges" in str(item.message)]


def test_saved_checkpoint_reloads_exact_predictions_and_enforces_schema(tmp_path):
    pytest.importorskip("tabm")
    x, y, sites = regression_data(32)
    fitted = learner().fit_learner(x, y, sites, seed=31, config=tiny_config(), epochs=2)
    expected = fitted.predictor.predict(x)
    path = tmp_path / "residual-tabm.pt"

    fitted.predictor.save(path)
    restored = learner().load_predictor(path)

    np.testing.assert_array_equal(restored.predict(x), expected)
    with pytest.raises(FileExistsError):
        fitted.predictor.save(path)
    with pytest.raises(ValueError, match="schema"):
        restored.predict(x[["water", "heat"]])
    with pytest.raises(ValueError, match="schema"):
        restored.predict(x[["heat"]])


@pytest.mark.parametrize(
    "bad_x",
    [
        pd.DataFrame({"x": [1.0, np.inf, 3.0]}),
        pd.DataFrame({"x": [1.0, -np.inf, 3.0]}),
        pd.DataFrame({"x": [1.0 + 2.0j, 2.0 + 0.0j, 3.0 + 0.0j]}),
        pd.DataFrame({"label": ["a", "b", "c"]}),
        pd.DataFrame({"constant": [1.0, 1.0, 1.0]}),
    ],
)
def test_invalid_feature_tables_fail_clearly(bad_x):
    y = np.asarray([1.0, 2.0, 3.0])
    sites = np.asarray(["a", "b", "c"])
    with pytest.raises((TypeError, ValueError)):
        learner().fit_learner(bad_x, y, sites, seed=1, config=tiny_config(n_bins=2), epochs=1)


def test_fit_rejects_invalid_modes_targets_sites_and_validation_overlap():
    x, y, sites = regression_data(20)
    xv, yv, sv = regression_data(12, prefix="valid")
    config = tiny_config()

    with pytest.raises(ValueError, match="exactly one"):
        learner().fit_learner(x, y, sites, seed=1, config=config)
    with pytest.raises(ValueError, match="exactly one"):
        learner().fit_learner(
            x, y, sites, seed=1, config=config, epochs=1, validation=(xv, yv, sv)
        )
    with pytest.raises(ValueError, match="epochs"):
        learner().fit_learner(x, y, sites, seed=1, config=config, epochs=0)
    with pytest.raises(ValueError, match="finite"):
        learner().fit_learner(x, np.where(np.arange(len(y)) == 0, np.nan, y), sites,
                              seed=1, config=config, epochs=1)
    with pytest.raises(ValueError, match="length"):
        learner().fit_learner(x, y[:-1], sites, seed=1, config=config, epochs=1)
    with pytest.raises(TypeError, match="strings"):
        learner().fit_learner(x, y, np.arange(len(y)), seed=1, config=config, epochs=1)

    overlapping = sv.copy()
    overlapping[0] = sites[0]
    with pytest.raises(ValueError, match="overlap"):
        learner().fit_learner(
            x,
            y,
            sites,
            seed=1,
            config=config,
            validation=(xv, yv, overlapping),
        )


def test_prediction_batches_preserve_real_tabm_outputs_and_bound_forward_rows():
    torch=pytest.importorskip('torch')
    pytest.importorskip('tabm')
    x,y,sites=regression_data(32)
    fitted=learner().fit_learner(x,y,sites,seed=37,config=tiny_config(),epochs=2)
    query,_,_=regression_data(23,prefix='query')
    model=fitted.predictor._model
    values=fitted.predictor.preprocessor.transform(query)
    with torch.inference_mode():
        reference=model(torch.from_numpy(values)).squeeze(-1).mean(dim=1).numpy().astype(np.float64)
    reference=reference*fitted.predictor.target_scale+fitted.predictor.target_mean
    rows=[]
    hook=model.register_forward_pre_hook(lambda module,args: rows.append(len(args[0])))
    try:
        actual=fitted.predictor.predict(query)
    finally:
        hook.remove()
    assert max(rows)<=fitted.predictor.config.batch_size
    assert sum(rows)==len(query)
    np.testing.assert_allclose(actual,reference,rtol=1e-6,atol=1e-6)
    np.testing.assert_array_equal(actual,fitted.predictor.predict(query))
    assert fitted.predictor.predict(query.iloc[:0]).shape==(0,)


def test_validation_batches_preserve_global_equal_site_mae(monkeypatch):
    torch=pytest.importorskip('torch')
    pytest.importorskip('tabm')
    x,y,sites=regression_data(32)
    xv,yv,_=regression_data(19,prefix='validation')
    # Unequal site counts and a short final batch catch a mean-of-batch-means bug.
    sv=np.asarray(['large']*15+['small_a']*2+['small_b']*2)
    config=tiny_config(max_epochs=1,patience=1)
    make_model=learner()._make_model
    validation_rows=[]
    def instrument_model(*args,**kwargs):
        model=make_model(*args,**kwargs)
        model.register_forward_pre_hook(lambda module,inputs:
            validation_rows.append(len(inputs[0])) if not module.training else None)
        return model
    monkeypatch.setattr(learner(),'_make_model',instrument_model)
    fitted=learner().fit_learner(x,y,sites,seed=41,config=config,validation=(xv,yv,sv))
    assert max(validation_rows)<=config.batch_size
    assert sum(validation_rows)==len(xv)
    with torch.inference_mode():
        values=fitted.predictor.preprocessor.transform(xv)
        prediction=fitted.predictor._model(torch.from_numpy(values)).squeeze(-1).mean(dim=1)
        prediction=prediction*fitted.predictor.target_scale+fitted.predictor.target_mean
    error=np.abs(prediction.numpy()-yv)
    expected=float(np.mean([error[:15].mean(),error[15:17].mean(),error[17:].mean()]))
    assert fitted.history[0]['validation_mae']==pytest.approx(expected,rel=1e-6,abs=1e-6)


def test_batched_validation_matches_unbatched_training_trajectory_and_selected_epoch(monkeypatch):
    pytest.importorskip('tabm')
    x,y,sites=regression_data(32)
    xv,yv,sv=regression_data(19,prefix='validation')
    config=tiny_config(max_epochs=6,patience=2)
    batched=learner().fit_learner(x,y,sites,seed=43,config=config,validation=(xv,yv+.7,sv))
    def unbatched(model,values,batch_size):
        return model(values).squeeze(-1).mean(dim=1)
    with monkeypatch.context() as patch:
        patch.setattr(learner(),'_predict_in_batches',unbatched)
        reference=learner().fit_learner(x,y,sites,seed=43,config=config,validation=(xv,yv+.7,sv))
    assert batched.best_epoch==reference.best_epoch
    assert len(batched.history)==len(reference.history)
    np.testing.assert_array_equal([r['train_loss'] for r in batched.history],
                                  [r['train_loss'] for r in reference.history])
    np.testing.assert_allclose([r['validation_mae'] for r in batched.history],
        [r['validation_mae'] for r in reference.history],rtol=1e-6,atol=1e-6)
    np.testing.assert_allclose(batched.predictor.predict(xv),reference.predictor.predict(xv),
                               rtol=1e-6,atol=1e-6)
