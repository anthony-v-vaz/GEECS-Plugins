from __future__ import annotations
import inspect
from typing import Optional, Union
from geecs_api.api_defs import VarAlias, AsyncResult
from geecs_api.devices.geecs_device import GeecsDevice
from geecs_api.interface import api_error


class GasJetBlade(GeecsDevice):
    # Singleton
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(GasJetBlade, cls).__new__(cls)
            cls.instance.__initialized = False
        return cls.instance

    def __init__(self):
        if self.__initialized:
            return
        self.__initialized = True

        super().__init__('U_ModeImagerESP')

        self.var_spans = {VarAlias('JetBlade'): (-17.5, -16.)}
        self.build_var_dicts()
        self.var_depth = self.var_names_by_index.get(0)[0]

    def state_depth(self) -> Optional[float]:
        return self._state_value(self.var_depth)

    def get_depth(self, exec_timeout: float = 2.0, sync=True) -> Optional[Union[float, AsyncResult]]:
        return self.get(self.var_depth, exec_timeout=exec_timeout, sync=sync)

    def set_depth(self, value: float, exec_timeout: float = 10.0, sync=True) -> Optional[Union[float, AsyncResult]]:
        var_alias = self.var_aliases_by_name[self.var_depth][0]
        value = self.coerce_float(var_alias, inspect.stack()[0][3], value)
        return self.set(self.var_depth, value=value, exec_timeout=exec_timeout, sync=sync)


if __name__ == '__main__':
    api_error.clear()

    # list experiment devices and variables

    # create gas jet object
