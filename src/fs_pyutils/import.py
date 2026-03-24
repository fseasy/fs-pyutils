import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Union


def import_module_from_path(
  module_name: str,
  file_path: Union[str, Path],
  *,
  register: bool = True,
) -> ModuleType:
  """
  Dynamically import a Python module from a file path.

  Parameters
  ----------
  module_name:
      Name to assign to the module (used in sys.modules).

  file_path:
      Path to the .py file.

  register:
      Whether to register the module in sys.modules.

  Returns
  -------
  ModuleType
      The imported module.

  Raises
  ------
  FileNotFoundError
  ImportError
  """

  path = Path(file_path)

  if not path.exists():
    raise FileNotFoundError(path)

  spec = spec_from_file_location(module_name, path)

  if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load module from {path}")

  module = module_from_spec(spec)

  if register:
    sys.modules[module_name] = module

  spec.loader.exec_module(module)

  return module
