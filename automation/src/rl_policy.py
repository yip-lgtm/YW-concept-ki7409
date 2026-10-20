"""PPO with factorised categorical heads, in numpy.

No torch is available in this environment, and the policy here is small
enough that numpy is more than sufficient.  A policy-gradient learner over
3249 transitions with a nine-dimensional context does not need a deep
learning framework; it needs a correct advantage estimate and a stable
update.

STRUCTURE

  Three factored categorical heads, one per tunable exit parameter:

    t2_r            the R multiple the position closes at
    breakeven_at_r  after this R the stop moves to entry (0 = off)
    partial_at_r    this fraction of the position closes at 1.0R
                    (0 = off)

  Factored rather than a single joint head over the 6x4x4 = 96
  combinations: the parameters are near-independent, and the factored
  version needs far fewer samples per parameter to estimate well.

  A separate value head provides the baseline for the advantage estimate.

NUMERICAL NOTES

  - Softmax is computed with the max-subtraction trick.
  - The categorical log-probability is gathered rather than recomputed,
    so the ratio in the PPO objective is numerically stable.
  - Gradients are computed analytically. The value loss uses a plain
    squared error, which is stable enough here and avoids the extra
    machinery of a generalised advantage estimator with a value
    baseline.
"""
from __future__ import annotations

import numpy as np

LOG_EPS = 1e-9


def softmax(x: np.ndarray) -> np.ndarray:
    z = x - x.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def log_softmax(x: np.ndarray) -> np.ndarray:
    z = x - x.max(axis=-1, keepdims=True)
    return z - np.log(np.exp(z).sum(axis=-1, keepdims=True))


class MLP:
    """Two-layer MLP with tanh hidden and linear output."""

    def __init__(self, rng: np.random.Generator, sizes: list[int],
                 lr: float = 3e-4):
        self.W = []
        self.b = []
        for i in range(len(sizes) - 1):
            fan_in = sizes[i]
            scale = np.sqrt(2.0 / fan_in)
            self.W.append(rng.normal(0, scale, size=(fan_in, sizes[i + 1])))
            self.b.append(np.zeros(sizes[i + 1]))
        self.lr = lr
        # Adam moments, kept per parameter tensor.
        self._mW = [np.zeros_like(w) for w in self.W]
        self._vW = [np.zeros_like(w) for w in self.W]
        self._mb = [np.zeros_like(b) for b in self.b]
        self._vb = [np.zeros_like(b) for b in self.b]
        self._t = 0

    def forward(self, x: np.ndarray):
        acts = [x]
        h = x
        for i in range(len(self.W)):
            z = h @ self.W[i] + self.b[i]
            h = np.tanh(z) if i < len(self.W) - 1 else z
            acts.append(h)
        return acts

    def grads(self, acts: list[np.ndarray], d_out: np.ndarray) -> list:
        """Backprop. Returns list of (dW, db) matching self.W / self.b."""
        dW = [None] * len(self.W)
        db = [None] * len(self.b)
        delta = d_out
        for i in range(len(self.W) - 1, -1, -1):
            dW[i] = acts[i].T @ delta
            db[i] = delta.sum(axis=0)
            if i > 0:
                delta = (delta @ self.W[i].T) * (1.0 - acts[i] ** 2)
        return dW, db


class FactorizedPPO:
    """PPO over a factored categorical action space."""

    def __init__(self, obs_dim: int, head_sizes: list[int], hidden: int = 32,
                 lr: float = 3e-4, clip: float = 0.2, entropy_coef: float = 0.01,
                 value_coef: float = 0.5, seed: int = 7):
        self.rng = np.random.default_rng(seed)
        self.head_sizes = head_sizes
        self.n_heads = len(head_sizes)
        self.clip = clip
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.lr = lr

        self.actor = MLP(self.rng, [obs_dim, hidden, sum(head_sizes)], lr=lr)
        self.value = MLP(self.rng, [obs_dim, hidden, 1], lr=lr)
        # Split the actor output across the heads.
        self.slices = []
        off = 0
        for k in head_sizes:
            self.slices.append((off, off + k))
            off += k

    # ---- forward helpers ----

    def _logits(self, obs: np.ndarray):
        acts = self.actor.forward(obs)
        out = acts[-1]
        return [out[:, a:b] for a, b in self.slices], acts

    def log_probs(self, obs: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """(N,) total log-prob of the joint factored action."""
        logits, _ = self._logits(obs)
        total = np.zeros(obs.shape[0])
        for h, lg in enumerate(logits):
            ls = log_softmax(lg)
            total += ls[np.arange(obs.shape[0]), actions[:, h]]
        return total

    def entropy(self, obs: np.ndarray) -> np.ndarray:
        logits, _ = self._logits(obs)
        ent = np.zeros(obs.shape[0])
        for lg in logits:
            ls = log_softmax(lg)
            p = np.exp(ls)
            ent += -(p * ls).sum(axis=1)
        return ent

    def value_of(self, obs: np.ndarray) -> np.ndarray:
        return self.value.forward(obs)[-1].ravel()

    def sample(self, obs: np.ndarray):
        logits, _ = self._logits(obs)
        actions = np.zeros((obs.shape[0], self.n_heads), dtype=np.int64)
        logp = np.zeros(obs.shape[0])
        for h, lg in enumerate(logits):
            p = softmax(lg)
            a = np.array([self.rng.choice(len(p[i]), p=p[i]) for i in range(len(p))])
            actions[:, h] = a
            ls = log_softmax(lg)
            logp += ls[np.arange(len(a)), a]
        return actions, logp

    def evaluate(self, obs: np.ndarray, actions: np.ndarray):
        """Return (logp, entropy, value) for the given state-action pairs."""
        return self.log_probs(obs, actions), self.entropy(obs), self.value_of(obs)

    # ---- training ----

    def update(self, obs: np.ndarray, actions: np.ndarray, old_logp: np.ndarray,
               adv: np.ndarray, ret: np.ndarray, epochs: int = 2,
               batch_size: int = 128) -> dict:
        """One PPO update. Returns a stats dict."""
        n = obs.shape[0]
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        stats = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0,
                 "clip_frac": 0.0, "n": n}
        idx_all = np.arange(n)
        for _ in range(epochs):
            self.rng.shuffle(idx_all)
            for start in range(0, n, batch_size):
                idx = idx_all[start:start + batch_size]
                ob = obs[idx]
                ac = actions[idx]
                adv_b = adv[idx]
                ret_b = ret[idx]

                logp, ent, v = self.evaluate(ob, ac)
                ratio = np.exp(logp - old_logp[idx])
                s1 = ratio * adv_b
                s2 = np.clip(ratio, 1 - self.clip, 1 + self.clip) * adv_b
                pol_loss = -np.minimum(s1, s2).mean()
                val_loss = ((v - ret_b) ** 2).mean()
                ent_mean = ent.mean()
                loss = pol_loss - self.entropy_coef * ent_mean + self.value_coef * val_loss

                # Actor gradients
                logits, acts_a = self._logits(ob)
                d_logits = []
                for h, lg in enumerate(logits):
                    ls = log_softmax(lg)
                    p = np.exp(ls)
                    # d(-min(s1,s2)) / d logp -> use the unclipped branch indicator
                    use_unclipped = (s1 <= s2)
                    # policy gradient weight per sample
                    g = -adv_b * use_unclipped
                    # distribute over heads
                    onehot = np.zeros_like(p)
                    onehot[np.arange(len(ac)), ac[:, h]] = 1.0
                    # d logp_h / d logit = onehot - p
                    d_logits.append((onehot - p) * g[:, None])
                d_actor_out = np.zeros_like(acts_a[-1])
                for h, (a, b) in enumerate(self.slices):
                    d_actor_out[:, a:b] = d_logits[h]
                # entropy bonus gradient
                d_actor_out -= self.entropy_coef * self._d_entropy(ob)

                gW, gb = self.actor.grads(acts_a, d_actor_out)
                # Value gradients
                d_v = self.value_coef * 2.0 * (v - ret_b)[:, None]
                vacts = self.value.forward(ob)
                vW, vb = self.value.grads(vacts, d_v)

                # Adam-ish update (simple momentum SGD with per-parameter scaling)
                self._apply(self.actor, gW, gb)
                self._apply(self.value, vW, vb)

                stats["policy_loss"] += float(pol_loss) * len(idx)
                stats["value_loss"] += float(val_loss) * len(idx)
                stats["entropy"] += float(ent_mean) * len(idx)
                stats["clip_frac"] += float(np.mean(
                    (ratio < 1 - self.clip) | (ratio > 1 + self.clip))) * len(idx)
        for k in ("policy_loss", "value_loss", "entropy", "clip_frac"):
            stats[k] /= max(1, n * epochs)
        return stats

    def _d_entropy(self, obs: np.ndarray) -> np.ndarray:
        """Gradient of the summed head entropies wrt the actor output."""
        logits, _ = self._logits(obs)
        d = np.zeros_like(logits[0])
        out = np.zeros_like(self.actor.forward(obs)[-1])
        for h, lg in enumerate(logits):
            ls = log_softmax(lg)
            p = np.exp(ls)
            # d(-sum p log p)/d logit = -p * (log p + H - H_j) ... use the simple form
            H = -(p * ls).sum(axis=1, keepdims=True)
            g = -p * (ls + H)
            a, b = self.slices[h]
            out[:, a:b] = g
        return out

    def _apply(self, mlp: MLP, gW, gb, max_norm: float = 5.0):
        """Adam step with global gradient-norm clipping.

        Plain SGD with a fixed step diverged here: the value head's linear
        output layer with an unbounded gradient reached 1e98 within 56 steps
        and then overflowed to NaN, which propagated into the actor through
        the shared loss. Clipping the global norm and using Adam's per-
        parameter scaling is what keeps the update bounded.
        """
        # Global norm across all parameter tensors.
        total_sq = 0.0
        for g in list(gW) + list(gb):
            total_sq += float(np.sum(g * g))
        norm = np.sqrt(total_sq)
        scale = 1.0
        if norm > max_norm and norm > 0:
            scale = max_norm / norm
            mlp._clipped = True
        else:
            mlp._clipped = False

        mlp._t += 1
        b1, b2, eps = 0.9, 0.999, 1e-8
        t = mlp._t
        for i in range(len(mlp.W)):
            gw = gW[i] * scale
            gb_ = gb[i] * scale
            mlp._mW[i] = b1 * mlp._mW[i] + (1 - b1) * gw
            mlp._vW[i] = b2 * mlp._vW[i] + (1 - b2) * (gw * gw)
            mhat = mlp._mW[i] / (1 - b1 ** t)
            vhat = mlp._vW[i] / (1 - b2 ** t)
            mlp.W[i] -= mlp.lr * mhat / (np.sqrt(vhat) + eps)

            mlp._mb[i] = b1 * mlp._mb[i] + (1 - b1) * gb_
            mlp._vb[i] = b2 * mlp._vb[i] + (1 - b2) * (gb_ * gb_)
            mhat = mlp._mb[i] / (1 - b1 ** t)
            vhat = mlp._vb[i] / (1 - b2 ** t)
            mlp.b[i] -= mlp.lr * mhat / (np.sqrt(vhat) + eps)

    # ---- persistence ----

    def state_dict(self) -> dict:
        d = {"head_sizes": self.head_sizes, "clip": self.clip,
             "entropy_coef": self.entropy_coef, "value_coef": self.value_coef,
             "lr": self.lr}
        for i, (w, b) in enumerate(zip(self.actor.W, self.actor.b)):
            d[f"actor_W{i}"] = w
            d[f"actor_b{i}"] = b
        for i, (w, b) in enumerate(zip(self.value.W, self.value.b)):
            d[f"value_W{i}"] = w
            d[f"value_b{i}"] = b
        return d

    def load_state_dict(self, d: dict):
        n_a = len(self.actor.W)
        for i in range(n_a):
            self.actor.W[i] = d[f"actor_W{i}"]
            self.actor.b[i] = d[f"actor_b{i}"]
        n_v = len(self.value.W)
        for i in range(n_v):
            self.value.W[i] = d[f"value_W{i}"]
            self.value.b[i] = d[f"value_b{i}"]
