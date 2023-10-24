"""
Gait bout acceleration pre-processing functions.

Lukas Adamowicz
Copyright (c) 2023, Pfizer Inc. All rights reserved
"""
from numpy import mean, std, median, argmax, sign, abs, argsort, corrcoef, diff, array
from scipy.signal import detrend, butter, sosfiltfilt, find_peaks

from skdh.base import BaseProcess, handle_process_returns
from skdh.utility import correct_accelerometer_orientation
from skdh.gait.gait_metrics import gait_metrics


class PreprocessGaitBout(BaseProcess):
    """
    Preprocess acceleration data for gait using the newer/V2 method.

    Parameters
    ----------
    correct_orientation : bool, optional
        Correct the accelerometer orientation if it is slightly mis-aligned
        with the anatomical axes. Default is True.
    filter_cutoff : float, optional
        Low-pass filter cutoff in Hz. Default is 20.0
    filter_order : int, optional
        Low-pass filter order. Default is 4.
    step_freq_filter_kw : {None, dict}, optional
        Key-word arguments for the filter applied to the acceleration data before
        autocorrelation when estimating the mean step frequency of the gait bout.
        If None (default), the following are used:

        - `N`: 4
        - `Wn`: [2 * 0.5, 2 * 5.0] - NOTE, this should be in Hz, not radians.
          fs will be passed into the filter setup at filter creation time.
        - `btype`: band
        - `output`: sos - NOTE that this will always be set/overriden

        See :scipy-signal:func:`scipy.signal.butter` for full options.
    """

    def __init__(self, correct_orientation=True, filter_cutoff=20.0, filter_order=4, step_freq_filter_kw=None):
        super().__init__(
            correct_orientation=correct_orientation,
            filter_cutoff=filter_cutoff,
            filter_order=filter_order,
        )

        self.corr_orient = correct_orientation
        self.filter_cutoff = filter_cutoff
        self.filter_order = filter_order

        if step_freq_filter_kw is None:
            step_freq_filter_kw = {
                'N': 4,
                'Wn': array([2 * 0.5, 2 * 5.0]),
                'btype': 'band',
            }

        step_freq_filter_kw.update({'output': 'sos'})
        self.sf_filter_kw = step_freq_filter_kw

    @staticmethod
    def get_ap_axis_sign(fs, accel, ap_axis):
        """
        Estimate the sign of the AP axis

        Parameters
        ----------
        fs : float
            Sampling frequency in Hz.
        accel : numpy.ndarray
        ap_axis : int
            Anterior-Posterior axis

        Returns
        -------
        ap_axis_sign : {-1, 1}
            Sign of the AP axis.
        """
        sos = butter(4, [2 * 0.25 / fs, 2 * 7.0 / fs], output="sos", btype="band")
        ap_acc_f = sosfiltfilt(sos, accel[:, ap_axis])

        mx, mx_meta = find_peaks(ap_acc_f, prominence=0.05)
        med_prom = median(mx_meta["prominences"])
        mask = mx_meta["prominences"] > (0.75 * med_prom)

        left_med = median(mx[mask] - mx_meta["left_bases"][mask])
        right_med = median(mx_meta["right_bases"][mask] - mx[mask])

        sign = -1 if (left_med < right_med) else 1

        return sign

    @handle_process_returns(results_to_kwargs=True)
    def predict(self, *, time, accel, fs=None, v_axis=None, ap_axis=None, **kwargs):
        """
        predict(time, accel, *, fs=None, v_axis=None, ap_axis=None)

        Parameters
        ----------
        time : numpy.ndarray
            (N, ) array of unix timestamps, in seconds
        accel : numpy.ndarray
            (N, 3) array of accelerations measured by a centrally mounted lumbar
            inertial measurement device, in units of 'g'.
        fs : float, optional
            Sampling frequency in Hz of the accelerometer data. If not provided,
            will be computed form the timestamps.
        v_axis : {None, 0, 1, 2}, optional
            Index of the vertical axis in the acceleration data. Default is None.
            If None, will be estimated from the acceleration data.
        ap_axis : {None, 0, 1, 2}, optional
            Index of the Anterior-Posterior axis in the acceleration data.
            Default is None. If None, will be estimated from the acceleration data.

        Returns
        -------
        results : dict
            Dictionary with the following items that can be used for future
            processing steps:

            - `v_axis`: provided or estimated vertical axis index.
            - `v_axis_est`: estimated vertical axis index.
            - `v_axis_sign`: sign of the vertical axis.
            - `ap_axis`: provided or estimated AP axis index.
            - `ap_axis_est`: estimated AP axis index.
            - `ap_axis_sign`: estimated sign of the AP axis.
            - `mean_step_freq`: estimated mean step frequency during this gait bout.
            - `accel_filt`: filtered and detrended acceleration for this gait bout.
        """
        # calculate fs if we need to
        fs = 1 / mean(diff(time)) if fs is None else fs

        # estimate accelerometer axes if necessary
        acc_mean = mean(accel, axis=0)
        v_axis_est = argmax(abs(acc_mean))  # always estimate for testing purposes
        if v_axis is None:
            v_axis = v_axis_est

        # always compute the sign
        v_axis_sign = sign(acc_mean[v_axis])

        # always estimate for testing purposes
        sos = butter(4, 2 * 3.0 / fs, output="sos")
        acc_f = sosfiltfilt(sos, accel, axis=0)

        ac = gait_metrics._autocovariancefn(
            acc_f, min(accel.shape[0] - 1, int(10 * fs)), biased=True, axis=0
        )

        ap_axis_est = argsort(corrcoef(ac.T)[v_axis])[-2]

        if ap_axis is None:
            ap_axis = ap_axis_est

        # always compute the sign
        ap_axis_sign = self.get_ap_axis_sign(fs, accel, ap_axis)

        if self.corr_orient:
            accel = correct_accelerometer_orientation(
                accel, v_axis=v_axis, ap_axis=ap_axis
            )

        # filter
        sos = butter(
            self.filter_order, 2 * self.filter_cutoff / fs, output="sos", btype="low"
        )
        accel_filt = sosfiltfilt(sos, accel, axis=0)

        # detrend
        accel_filt = detrend(accel_filt, axis=0)

        # estimate step frequency
        sos = butter(**self.sf_filter_kw, fs=fs)
        sf_acc_f = sosfiltfilt(sos, accel, axis=0)

        ac = gait_metrics._autocovariancefn(
            sf_acc_f, min(sf_acc_f.shape[0] - 1, int(4 * fs)), biased=True, axis=0
        )

        factor = 1.0
        pks = array([])
        while factor > 0.5 and pks.size == 0:
            pks, _ = find_peaks(ac[:, ap_axis], prominence=factor * std(ac[:, ap_axis]))
            factor -= 0.05

        idx = argsort(ac[pks, ap_axis])[-1]

        step_samples = pks[idx]
        mean_step_freq = 1 / (step_samples / fs)
        # constrain the step frequency
        mean_step_freq = max(min(mean_step_freq, 5.0), 0.4)

        res = {
            "v_axis": v_axis,
            "v_axis_est": v_axis_est,
            "v_axis_sign": v_axis_sign,
            "ap_axis": ap_axis,
            "ap_axis_est": ap_axis_est,
            "ap_axis_sign": ap_axis_sign,
            "mean_step_freq": mean_step_freq,
            "accel_filt": accel_filt,
        }

        return res