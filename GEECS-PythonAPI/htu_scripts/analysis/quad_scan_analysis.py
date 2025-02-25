import numpy as np
from numpy.polynomial.polynomial import polyfit
from pathlib import Path
import matplotlib.pyplot as plt
from typing import Union, Any, Optional
from geecs_api.api_defs import ScanTag
import geecs_api.experiment.htu as htu
from geecs_api.tools.scans.scan_data import ScanData
from geecs_api.tools.interfaces.prompts import text_input
from geecs_api.tools.scans.scan_images import ScanImages
from geecs_api.tools.scans import ScanAnalysis
from geecs_api.tools.interfaces.exports import save_py
from geecs_api.tools.images.displays import polyfit_label
# from geecs_api.devices.HTU.transport.magnets import Quads


class QuadAnalysis(ScanAnalysis):
    def __init__(self, scan_data: ScanData, scan_images: ScanImages,
                 quad: int, fwhms_metric: str = 'median', quad_2_screen: float = 1.):
        super().__init__(scan_data, scan_images, 'U_EMQTripletBipolar')
        self.quad_number: int = quad
        self.quad_variable: str = f'Current_Limit.Ch{quad}'

        self.fwhms_metric: str = fwhms_metric
        self.quad_2_screen: float = quad_2_screen

    def analyze(self, variable: Optional[str] = None, com_threshold: float = 0.5,
                bkg_image: Optional[Union[Path, np.ndarray]] = None, ask_rerun: bool = True,
                blind_loads: bool = False, store_images: bool = True, store_scalars: bool = True,
                save_plots: bool = False, save: bool = False) -> Optional[Path]:
        if not variable:
            variable = self.quad_variable

        super().analyze(variable, com_threshold, bkg_image, ask_rerun, blind_loads,
                        store_images, store_scalars, save_plots, False)

        figs = super().render(physical_units=True, x_label='Current [A]',
                              show_xy=True, show_fwhms=True, show_deltas=False,
                              xy_metric='median', fwhms_metric=self.fwhms_metric, deltas_metric='mean',
                              xy_fit=1, fwhms_fit=2, deltas_fit=0,
                              show_figs=True, save_dir=self.scan_data.get_analysis_folder(), sync=False)

        setpoints: np.ndarray = self.data_dict['setpoints']
        range_x = np.array([np.min(setpoints), np.max(setpoints)])
        range_y = np.array([np.min(setpoints), np.max(setpoints)])

        while True:
            try:
                lim_str = text_input(f'Lower current limit to consider for FWHM-X, e.g. "none" or -1.5 : ')
                lim_low = np.min(setpoints) if lim_str.lower() == 'none' else float(lim_str)
                lim_str = text_input(f'Upper current limit to consider for FWHM-X, e.g. "none" or 3.5 : ')
                lim_high = np.max(setpoints) if lim_str.lower() == 'none' else float(lim_str)
                range_x = np.array([lim_low, lim_high])

                lim_str = text_input(f'Lower current limit to consider for FWHM-Y, e.g. "none" or -1.5 : ')
                lim_low = np.min(setpoints) if lim_str.lower() == 'none' else float(lim_str)
                lim_str = text_input(f'Upper current limit to consider for FWHM-Y, e.g. "none" or 3.5 : ')
                lim_high = np.max(setpoints) if lim_str.lower() == 'none' else float(lim_str)
                range_y = np.array([lim_low, lim_high])

                break
            except Exception:
                continue
            finally:
                try:
                    for fig_ax in figs:
                        plt.close(fig_ax[0])
                except Exception:
                    pass

        selected_x: np.ndarray = (setpoints >= np.min(range_x)) * (setpoints <= np.max(range_x))
        scan_x = setpoints[selected_x]

        selected_y: np.ndarray = (setpoints >= np.min(range_y)) * (setpoints <= np.max(range_y))
        scan_y = setpoints[selected_y]

        sample_analysis = self.data_dict['analyses'][0]
        um_per_pix: float = sample_analysis['summary']['um_per_pix']
        positions: {} = sample_analysis['image_analyses'][0]['positions']
        twiss_analysis: dict[str, Any] = {}

        for pos in positions['short_names']:
            twiss_analysis[pos] = {}
            data_val, data_err_low, data_err_high = ScanAnalysis.fetch_metrics(self.data_dict['analyses'],
                                                                               self.fwhms_metric, 'fwhms',
                                                                               pos, 'pix_ij', um_per_pix)
            twiss_analysis[pos]['fwhms'] = (data_val, data_err_low, data_err_high)

            # noinspection PyTypeChecker
            fit_x_pars: np.ndarray = np.flip(polyfit(scan_x, data_val[selected_x, 1], 2))
            twiss_analysis[pos]['epsilon_x'], twiss_analysis[pos]['alpha_x'], twiss_analysis[pos]['beta_x'] = \
                QuadAnalysis.twiss_parameters(fit_x_pars * 1e-6, self.quad_2_screen)

            # noinspection PyTypeChecker
            fit_y_pars: np.ndarray = np.flip(polyfit(scan_y, data_val[selected_y, 0], 2))
            twiss_analysis[pos]['epsilon_y'], twiss_analysis[pos]['alpha_y'], twiss_analysis[pos]['beta_y'] = \
                QuadAnalysis.twiss_parameters(fit_y_pars * 1e-6, self.quad_2_screen)

            twiss_analysis[pos]['fit_pars'] = np.stack([fit_y_pars, fit_x_pars]).transpose()

        twiss_analysis['quad_2_screen'] = self.quad_2_screen
        twiss_analysis['indexes_selected'] = np.stack([selected_y, selected_x]).transpose()
        twiss_analysis['setpoints_selected'] = np.stack([range_y, range_x]).transpose()
        self.data_dict['twiss'] = twiss_analysis

        if save:
            export_file_path = self.scan_data.get_analysis_folder() / f'quad_scan_analysis_{self.device_name}'
            save_py(file_path=export_file_path, data=self.data_dict)
            print(f'Data exported to:\n\t{export_file_path}.dat')
        else:
            export_file_path = None

        return export_file_path

    def render_twiss(self, physical_units: bool = True, save_dir: Optional[Path] = None):
        if 'twiss' not in self.data_dict:
            return []

        twiss = self.data_dict['twiss']

        units_factor: float
        units_label: str

        sample_analysis = self.data_dict['analyses'][0]
        um_per_pix: float = sample_analysis['summary']['um_per_pix']
        positions: {} = sample_analysis['image_analyses'][0]['positions']

        plot_labels = ['X', 'Y']

        for i_ax, (pos, title) in enumerate(zip(positions['short_names'], positions['long_names'])):
            try:
                fig, axs = plt.subplots(ncols=1, nrows=1, sharex='col',
                                        figsize=(ScanImages.fig_size[0], ScanImages.fig_size[1]))
                if physical_units:
                    if (np.max(twiss[pos]['fwhms'][0]) - np.min(twiss[pos]['fwhms'][0])) > 1000:
                        units_factor = 0.001
                        units_label = 'mm'
                    else:
                        units_factor = 1
                        units_label = r'$\mu$m'
                else:
                    units_factor = 1
                    units_label = 'pix'

                for i_xy, var, c_fill, c_val in zip([1, 0], plot_labels, ['m', 'y'], ['b', 'g']):
                    indexes = twiss['indexes_selected'][:, i_xy]

                    axs.fill_between(self.data_dict['setpoints'],
                                     units_factor * (twiss[pos]['fwhms'][0][:, i_xy] - twiss[pos]['fwhms'][1][:, i_xy]),
                                     units_factor * (twiss[pos]['fwhms'][0][:, i_xy] + twiss[pos]['fwhms'][2][:, i_xy]),
                                     color='gray', alpha=0.166)
                    axs.plot(self.data_dict['setpoints'],
                             units_factor * twiss[pos]['fwhms'][0][:, i_xy], f'o-',
                             color='gray', linewidth=1, markersize=3)

                    axs.fill_between(self.data_dict['setpoints'][indexes],
                                     units_factor * (twiss[pos]['fwhms'][0][indexes, i_xy]
                                                     - twiss[pos]['fwhms'][1][indexes, i_xy]),
                                     units_factor * (twiss[pos]['fwhms'][0][indexes, i_xy]
                                                     + twiss[pos]['fwhms'][2][indexes, i_xy]),
                                     color=c_fill, alpha=0.33)
                    axs.plot(self.data_dict['setpoints'][indexes],
                             units_factor * twiss[pos]['fwhms'][0][indexes, i_xy], f'o{c_val}-',
                             label=rf'{var} ({self.fwhms_metric}) [{units_label}]', linewidth=1, markersize=3)

                    fit_vals = np.polyval(twiss[pos]['fit_pars'][:, i_xy], self.data_dict['setpoints'][indexes])
                    axs.plot(self.data_dict['setpoints'][indexes], fit_vals, 'k', linestyle='--', linewidth=0.66,
                             label=rf'$\epsilon_{var.lower()}$ = {twiss[pos][f"epsilon_{var.lower()}"]:.2f}, '
                                   + rf'$\alpha_{var.lower()}$ = {twiss[pos][f"alpha_{var.lower()}"]:.2f}, '
                                   + rf'$\beta_{var.lower()}$ = {twiss[pos][f"beta_{var.lower()}"]:.2f}' + '\nfit: '
                                   + polyfit_label(list(twiss[pos]['fit_pars'][:, i_xy]), res=2, latex=True))

                axs.legend(loc='best', prop={'size': 8})
                axs.set_ylabel(f'FWHMs [{units_label}]')
                axs.set_title(rf'{title} ({um_per_pix:.2f} $\mu$m/pix)')
                axs.set_xlabel('Current [A]')

                if save_dir:
                    save_path = save_dir / f'quad_scan_analysis_{pos}_{self.fwhms_metric}.png'
                    plt.savefig(save_path, dpi=300)

            except Exception:
                pass

        plt.show(block=True)

    @staticmethod
    def twiss_parameters(poly_pars, quad_2_screen: float = 1.) -> tuple[float, float, float]:
        a1 = poly_pars[0]
        a2 = poly_pars[1] / (-2 * a1)
        a3 = poly_pars[2] - (a1 * a2**2)

        epsilon = np.sqrt(a1 * a3) / (quad_2_screen**2)
        beta = np.sqrt(a1 / a3)
        alpha = (a2 + 1/quad_2_screen) * beta

        return epsilon, alpha, beta


if __name__ == '__main__':
    # database
    # --------------------------------------------------------------------------
    _base_path, is_local = htu.initialize()
    _base_tag = ScanTag(2023, 7, 6, 49)

    # _device = Quads()
    # _camera = Camera('UC_TopView')
    _device = 'U_EMQTripletBipolar'
    _camera = 'A3'

    _quad = 3

    _folder = ScanData.build_folder_path(_base_tag, _base_path)
    _scan_data = ScanData(_folder, ignore_experiment_name=is_local)
    _scan_images = ScanImages(_scan_data, _camera)
    _quad_analysis = QuadAnalysis(_scan_data, _scan_images, _quad, fwhms_metric='median', quad_2_screen=2.126)

    # scan analysis
    # --------------------------------------------------------------------------
    _path = _quad_analysis.analyze('', com_threshold=0.5, bkg_image=None, ask_rerun=False, blind_loads=True,
                                   store_images=False, store_scalars=False, save_plots=False, save=True)

    _quad_analysis.render_twiss(physical_units=True, save_dir=_quad_analysis.scan_data.get_analysis_folder())

    # _device.close()
    # _camera.close()
    print('done')
