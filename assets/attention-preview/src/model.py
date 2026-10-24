"""Original one-dimensional Attention example; frame intervals are half-open."""
from math import exp, log


def attention_state(local_frame: int, fps: int) -> dict[str, float]:
    """Compute inputs, unshifted exponentials, stable weights and output afresh."""
    if type(fps) is not int or fps <= 0:
        raise ValueError("fps must be a positive integer")
    if type(local_frame) is not int or not 0 <= local_frame < 55 * fps:
        raise ValueError("local_frame must be an integer in [0, 55*fps)")
    t = local_frame / fps
    peak = log(3)

    def between(start, end, a, b):
        u = (t - start) / (end - start)
        return a + (b - a) * u*u*(3 - 2*u)

    v2 = 6.0
    if t < 10:
        q = 0.0
    elif t < 25:
        q = between(10, 25, 0.0, peak)
    elif t < 38:
        q = between(25, 38, peak, -peak)
    elif t < 42:
        q = between(38, 42, -peak, peak)
    else:
        q = peak
        v2 = between(42, 50, 6.0, 10.0) if t < 50 else 10.0
    k1, k2, v1 = 0.0, 1.0, 2.0
    # k1 is exactly zero: retain canonical +0 so the fixed score reads 0.00.
    s1, s2 = 0.0, q*k2
    maximum = max(s1, s2)
    shifted1, shifted2 = exp(s1-maximum), exp(s2-maximum)
    total = shifted1 + shifted2
    a1, a2 = shifted1/total, shifted2/total
    return dict(q=q, k1=k1, k2=k2, v1=v1, v2=v2, s1=s1, s2=s2,
                e1=exp(s1), e2=exp(s2), a1=a1, a2=a2, y=a1*v1+a2*v2)
