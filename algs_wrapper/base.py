import re
import abc
import logging
from pathlib import Path
from typing import Union
from functools import partial

from utils.file_io import load_cfg, glob_file
from utils.processing import timer, parallel
from evaluator.metrics import ViewIndependentMetrics

logger = logging.getLogger(__name__)

class Base(metaclass=abc.ABCMeta):
    def __init__(self, algs_cfg_file, use_gpu=False) -> None:
        self._algs_cfg = load_cfg(Path(algs_cfg_file).resolve())
        self._use_gpu = use_gpu

    @abc.abstractmethod
    def encode(self):
        return NotImplemented

    @abc.abstractmethod
    def decode(self):
        return NotImplemented

    @property
    def rate(self) -> str:
        """Specify the set of bitrate control coding parameters. 
        The related coding parameters need to be configured in the 
        corresponding PCC algs config file.
        
        Returns
        -------
        `str`
            Tag of the rate control set.
        """
        return self._rate

    @rate.setter
    def rate(self, rate: str) -> None:
        m = re.search('^r[1-9]+', rate, re.MULTILINE)
        if m is None:
            logger.warning(
                f"Invalid rate control parameters. Use 'r1', 'r2', etc."
            )
        self._rate = m.group()

    def run_dataset(
            self,
            ds_name: str,
            exp_dir: Union[str, Path],
            ds_cfg_file: Union[str, Path] = 'cfgs/datasets.yml'
        ) -> None:
        """Run the experiments on dataset `ds_name` in the ``exp_dir``.
        
        Parameters
        ----------
        ds_name : `str`
            The name of the dataset (stored in 'cfgs/datasets.yml').
        exp_dir : `Union[str, Path]`
            The directory to store experiments results.
        use_gpu : `bool`, optional
            True for running GPU-depentdent PCC algorithm, False 
            otherwise. Defaults to False.
        ds_cfg_file : `Union[str, Path]`, optional
            The YAML config file of datasets. Defaults to 
            'cfgs/datasets.yml'.
        """
        exp_dir = Path(exp_dir).joinpath(self._rate)
        
        logger.info(
            f"Start to run experiments on {ds_name} dataset "
            f"with {type(self).__name__} in {exp_dir}"
        )

        if ds_cfg_file == 'cfgs/datasets.yml':
            ds_cfg_file = (
                Path(__file__).parent.parent.joinpath(ds_cfg_file).resolve()
            )
        ds_cfg = load_cfg(ds_cfg_file)

        pc_files = glob_file(
            ds_cfg[ds_name]['dataset_dir'],
            ds_cfg[ds_name]['test_pattern'],
            verbose=True
        )

        prun = partial(
            self.run,
            src_dir=ds_cfg[ds_name]['dataset_dir'],
            nor_dir=ds_cfg[ds_name]['dataset_w_normal_dir'],
            exp_dir=exp_dir,
            color=ds_cfg[ds_name]['color'],
            resolution=ds_cfg[ds_name]['resolution']
        )

        parallel(prun, pc_files, self._use_gpu)

    def run(
            self,
            pcfile: Union[str, Path],
            src_dir: Union[str, Path],
            nor_dir: Union[str, Path],
            exp_dir: Union[str, Path],
            color: int = 0,
            resolution: int = None
        ) -> None:
        """Run a single experiment on the given ``pcfile`` and save the 
        experiment results and evaluation log into ``exp_dir``.
        
        Parameters
        ----------
        pcfile : `Union[str, Path]`
            The relative path to ``src_dir`` of input point cloud.
        src_dir : `Union[str, Path]`
            The directory of input point cloud.
        nor_dir : `Union[str, Path]`
            The directory of input point cloud with normal. (Necessary 
            for p2plane metrics.)
        exp_dir : `Union[str, Path]`
            The directory to store experiments results.
        color : `int`, optional
            1 for calculating color metric, 0 otherwise. Defaults to 0.
        resolution : `int`, optional
            Maximum NN distance of the ``pcfile``. If the resolution is 
            not specified, it will be calculated on the fly. Defaults to
            None.
        """
        self._color = color
        self._resolution = resolution
        
        in_pcfile, nor_pcfile, bin_file, out_pcfile, evl_log = (
            self.__set_filepath(pcfile, src_dir, nor_dir, exp_dir)
        )

        enc_time = timer(self.encode, str(in_pcfile), str(bin_file))
        dec_time = timer(self.decode, str(bin_file), str(out_pcfile))

        # grab all the encoded binary files with same filename, but 
        # different suffix
        bin_files = glob_file(
            bin_file.parent, bin_file.stem+'*', fullpath=True
        )

        VIMetrics = ViewIndependentMetrics()
        ret = VIMetrics.evaluate(
            nor_pcfile,
            out_pcfile,
            color,
            resolution,
            enc_time,
            dec_time,
            bin_files
        )
        with open(evl_log, 'w') as f:
            f.write(ret)

    def __set_filepath(
            self, 
            pcfile: Union[str, Path],
            src_dir: Union[str, Path],
            nor_dir: Union[str, Path],
            exp_dir: Union[str, Path]
        ) -> tuple[Path, Path, Path, Path]:
        """Set up the experiment file paths, including encoded binary, 
        decoded point cloud, and evaluation log.
        
        Parameters
        ----------
        pcfile : `Union[str, Path]`
            The relative path of input point cloud.
        src_dir : `Union[str, Path]`
            The directory of input point cloud.
        nor_dir : `Union[str, Path]`
            The directory of input point cloud with normal. (Necessary 
            for p2plane metrics.)
        exp_dir : `Union[str, Path]`
            The directory to store experiments results.
        
        Returns
        -------
        `tuple[Path, Path, Path, Path]`
            The full path of input point cloud, encoded binary file,
            output point cloud, and evaluation log file.
        """
        in_pcfile = Path(src_dir).joinpath(pcfile)
        nor_pcfile = Path(nor_dir).joinpath(pcfile)
        bin_file = (
            Path(exp_dir)
            .joinpath('bin', pcfile).with_suffix(self._algs_cfg['bin_suffix'])
        )
        out_pcfile = Path(exp_dir).joinpath('dec', pcfile)
        evl_log = Path(exp_dir).joinpath('evl', pcfile).with_suffix('.log')
        
        bin_file.parent.mkdir(parents=True, exist_ok=True)
        out_pcfile.parent.mkdir(parents=True, exist_ok=True)
        evl_log.parent.mkdir(parents=True, exist_ok=True)

        return in_pcfile, nor_pcfile, bin_file, out_pcfile, evl_log