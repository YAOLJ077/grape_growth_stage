"""Daily responses: Fila (2014), Eq. 1; triangular chilling as documented."""
import numpy as np


def _temperatures(temperature):
    values = np.asarray(temperature, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Temperatures must be finite; missing days cannot be zero-filled")
    return values


def _cardinals(minimum, optimum, maximum):
    if not np.isfinite([minimum, optimum, maximum]).all() or not minimum < optimum < maximum:
        raise ValueError("Cardinal temperatures must be finite and minimum < optimum < maximum")


def linear(temperature, base):
    """Growing degree days (degrees Celsius per daily time step)."""
    if not np.isfinite(base):
        raise ValueError("Base temperature must be finite")
    return np.maximum(_temperatures(temperature) - base, 0.0)


def beta(temperature, minimum, optimum, maximum):
    """Fila beta response: zero outside the cardinals, one at the optimum."""
    _cardinals(minimum, optimum, maximum)
    values = _temperatures(temperature)
    result = np.zeros_like(values)
    active = (values > minimum) & (values < maximum)
    t = values[active]
    exponent = (optimum - minimum) / (maximum - optimum)
    # Evaluate only interior temperatures: fractional powers of negatives are invalid.
    log_rate = (np.log((maximum - t) / (maximum - optimum))
                + exponent * np.log((t - minimum) / (optimum - minimum)))
    result[active] = np.exp(np.minimum(log_rate, 0.0))
    return result


def triangular(temperature, minimum, optimum, maximum):
    """Bounded, normalized piecewise-linear chilling response."""
    _cardinals(minimum, optimum, maximum)
    t = _temperatures(temperature)
    return np.maximum(0.0, np.minimum((t - minimum) / (optimum - minimum),
                                    (maximum - t) / (maximum - optimum)))
