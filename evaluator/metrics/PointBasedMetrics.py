import re
import subprocess as sp
from pathlib import Path
from typing import Union, List, Tuple


import open3d as o3d

from libs.metric_base import MetricBase
from evaluator.dependencies.gdiam_wrapper import findMaxNNdistance

import open_pcc_metric.metric

class PointBasedMetrics(MetricBase):
    """Class for evaluating view independent metrics of given point
    clouds.

    View Independent Metrics:
        ACD (1->2), ACD (2->1),
        CD,
        CD-PSNR,
        Hausdorff,
        Y-CPSNR, U-CPSNR, V-CPSNR,
        Hybrid geo-color
    """

    def __init__(
            self,
            ref_pc: Union[str, Path],
            target_pc: Union[str, Path]
        ) -> None:
        super().__init__(ref_pc, target_pc)
        self._pc_error_bin = (
            Path(__file__).parents[1].
            joinpath("dependencies/mpeg-pcc-dmetric-master/test/pc_error")
            .resolve()
        )

    def evaluate(self) -> str:
        """Run the evaluation and generate the formatted evaluation
        results.

        Parameters
        ----------
        ref_pc : `Union[str, Path]`
            Full path of the reference point cloud. Use point cloud with
            normal to calculate the p2plane metrics.
        target_pc : `Union[str, Path]`
            Full path of the target point.
        color : `bool`, optional
            True for calculating color metric, false otherwise. Defaults
            to false.
        resolution : `int`, optional
            Maximum NN distance of the ``ref_pc``. If the resolution is
            not specified, it will be calculated on the fly. Defaults to
            None.
        enc_t : `float`, optional
            Total encoding time. Defaults to None.
        dec_t : `float`, optional
            Total decoding time. Defaults to None.
        bin_files : `List[Union[str, Path]]`, optional
            List of the full path of the encoded binary file. Used for
            calculate the compression ratio and bpp.

        Returns
        -------
        `str`
            The formatted evaluation results.
        """

        self._get_quality_metrics()

        ret = '\n'.join(self._results)

        return ret

    def _get_quality_metrics(self)-> None:
        """Calculate and parse the results of quality metrics from
        pc_error.
        """
        options = open_pcc_metric.metric.CalculateOptions(
            color="ycc" if self._has_color else None,
            hausdorff=True,
            point_to_plane=True,
        )

        open_pcc_metric.metric.AbstractMetric._instances = []
        res = open_pcc_metric.metric.calculate_from_files(
            str(self._ref_pc),
            str(self._target_pc),
            options,
        ).as_dict()

        # Related to source code starting from `evaluator/dependencies
        # /mpeg-pcc-dmetric-master/source/pcc_distortion.cpp:826`
        # chosen_metrics = [
        #     'ACD1      (p2point): ',
        #     'ACD2      (p2point): ',
        #     'CD        (p2point): ',
        #     'CD,PSNR   (p2point): ',
        #     'h.        (p2point): ',
        #     'ACD1      (p2plane): ',
        #     'ACD2      (p2plane): ',
        #     'CD        (p2plane): ',
        #     'CD,PSNR   (p2plane): ',
        #     'h.        (p2plane): ',
        # ]
        # if self._has_color:
        #     chosen_metrics += [
        #         'c[0],PSNRF         : ',
        #         'c[1],PSNRF         : ',
        #         'c[2],PSNRF         : ',
        #         'hybrid geo-color   : ',
        #     ]

        # chosen_metrics = [re.escape(pattern) for pattern in chosen_metrics]

        # found_val = []

        # for pattern in chosen_metrics:
        #     isfound = False
        #     for line in ret.splitlines():
        #         m = re.search(f'(?<={pattern}).*', line)
        #         if m:
        #             found_val.append(m.group())
        #             isfound = True
        #             break
        #     if isfound is False:
        #         found_val.append('nan')

        # assert len(found_val) == len(chosen_metrics)

        geo_mse_p2point_left = res["GeoMSE(p2point)(left)"]
        geo_mse_p2point_right = res["GeoMSE(p2point)(right)"]
        geo_mse_p2point_symm = res["GeoMSE(p2point)(symmetric)"]
        geo_psnr_p2point_symm = res["GeoPSNR(p2point)(symmetric)"]
        geo_haus_p2point_symm = res["GeoHausdorffDistance(p2point)(symmetric)"]
        lines = [
            f"========== Point-based Metrics =========",
            f"Asym. Chamfer dist. (1->2) p2pt: {geo_mse_p2point_left}",
            f"Asym. Chamfer dist. (2->1) p2pt: {geo_mse_p2point_right}",
            f"Chamfer dist.              p2pt: {geo_mse_p2point_symm}",
            f"CD-PSNR (dB)               p2pt: {geo_psnr_p2point_symm}",
            f"Hausdorff distance         p2pt: {geo_haus_p2point_symm}",
            "\n",
        ]
        if self._has_normal:
            geo_mse_p2plane_left = res["GeoMSE(p2plane)(left)"]
            geo_mse_p2plane_right = res["GeoMSE(p2plane)(right)"]
            geo_mse_p2plane_symm = res["GeoMSE(p2plane)(symmetric)"]
            geo_psnr_p2plane_symm = res["GeoPSNR(p2plane)(symmetric)"]
            geo_haus_p2plane_symm = res["GeoHausdorffDistance(p2plane)(symmetric)"]
            lines += [
                f"----------------------------------------",
                f"Asym. Chamfer dist. (1->2) p2pl: {geo_mse_p2plane_left}",
                f"Asym. Chamfer dist. (2->1) p2pl: {geo_mse_p2plane_right}",
                f"Chamfer dist.              p2pl: {geo_mse_p2plane_symm}",
                f"CD-PSNR (dB)               p2pl: {geo_psnr_p2plane_symm}",
                f"Hausdorff distance         p2pl: {geo_haus_p2plane_symm}",
                "\n",
            ]
        if self._has_color:
            y_color_psnr = res["ColorPSNR(symmetric)"][0]
            u_color_psnr = res["ColorPSNR(symmetric)"][1]
            v_color_psnr = res["ColorPSNR(symmetric)"][2]
            lines += [
                f"----------------------------------------",
                f"Y-CPSNR (dB)                   : {y_color_psnr}",
                f"U-CPSNR (dB)                   : {u_color_psnr}",
                f"V-CPSNR (dB)                   : {v_color_psnr}",
                "\n",
            ]
        if self._has_color and self._has_normal:
            lines += [
                f"============== QoE Metric ==============",
                f"Hybrid geo-color               : 0.0",
                "\n",
            ]

        self._results += lines

    def _pc_error_wrapper(self) -> str:
        """Wrapper of the metric software, which modifies the formulas
        and adds new metrics based on mpeg-pcc-dmetric.

        Returns
        -------
        `str`
            The result of objective quality metrics.
        """
        # [TODO]
        # Integrate findMaxNNdistance into mpeg-pcc-dmetric
        if self._resolution is None:
            self._resolution = findMaxNNdistance(self._ref_pc)

        cmd = [
            self._pc_error_bin,
            f'--fileA={self._ref_pc}',
            f'--fileB={self._target_pc}',
            f'--color={1 if self._has_color else 0}',
            '--hausdorff=1',
            f'--resolution={self._resolution}',
        ]

        ret = sp.run(cmd, capture_output=True, universal_newlines=True)

        return ret.stdout