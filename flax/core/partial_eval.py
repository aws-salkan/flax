from typing import Any

import functools

import jax
from jax import linear_util as lu
from jax.interpreters import partial_eval as pe

from flax import errors


def _maybe_unknown(x: Any) -> pe.PartialVal:
  if isinstance(x, jax.ShapeDtypeStruct):
    return pe.PartialVal.unknown(jax.ShapedArray(x.shape, x.dtype))
  else:
    return pe.PartialVal.known(x)


def lazy_init(fn):
  """Lazily evaluate a function by using the shapes of the inputs.

  The returned function accepts a combination of JAX values and
  ``jax.ShapeDtypeStruct`` instances for the inputs for which we
  don't need concrete values (only the shape and dtype).

  This API is used by ``core.lazy_init`` or ``Module.lazy_init``
  to initialize variables without doing any actual compute on the
  inputs.

  Args:
    fn: the function to be lazily evaluated.
  Returns:
    A new function that accepts a mix of concrete valeus and
    ``jax.ShapeDtypeStruct`` instances.
  """
  @functools.wraps(fn)
  def wrapper(*args, **kwargs):
    # TODO(mattjj,jheek): use a public JAX API
    # flatten fn and prepare for internal JAX transform
    inputs_flat, in_tree = jax.tree_util.tree_flatten((args, kwargs))
    f_flat, out_tree = jax.api_util.flatten_fun(lu.wrap_init(fn), in_tree)
    # map inputs to PartialVal known/unknown
    # only compute depending on knowns will be computed
    in_pvals = [_maybe_unknown(x) for x in inputs_flat]
    _, out_pvals, _ = pe.trace_to_jaxpr_nounits(f_flat, in_pvals)
    # all outputs should be knowns. If this fails
    # the user is creating variables that depend on a
    # argument that was passed as a ShapeDtypeStruct.
    out_flat = []
    for pv, const in out_pvals:
      if pv is None:
        # const is the actual value of the known output
        out_flat.append(const)
      else:
        raise errors.LazyInitError(pv)
    return jax.tree_util.tree_unflatten(out_tree(), out_flat)

  return wrapper
