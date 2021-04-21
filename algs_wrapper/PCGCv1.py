from typing import Union
from pathlib import Path
from multiprocessing.managers import BaseProxy

from algs_wrapper.base import Base
from utils.file_io import glob_file
from evaluator.metrics import ViewIndependentMetrics

class PCGCv1(Base):
    def __init__(self):
        super().__init__()

    def make_encode_cmd(self, in_pcfile, bin_file):
        cmd = [
            self._algs_cfg['python'],
            self._algs_cfg['test_script'],
            'compress',
            in_pcfile,
            bin_file,
            '--ckpt_dir', self._algs_cfg[self.rate]['ckpt_dir'],
            '--scale', str(self._algs_cfg[self.rate]['scale']),
            '--rho', str(self._algs_cfg[self.rate]['rho'])
        ]
        
        return cmd

    def make_decode_cmd(self, bin_file, out_pcfile):
        cmd = [
            self._algs_cfg['python'],
            self._algs_cfg['test_script'],
            'decompress',
            bin_file,
            out_pcfile,
            '--ckpt_dir', self._algs_cfg[self.rate]['ckpt_dir'],
            '--scale', str(self._algs_cfg[self.rate]['scale']),
            '--rho', str(self._algs_cfg[self.rate]['rho'])
        ]

        return cmd
    
    # Overwriting the base class method due to the compressed binary 
    # file format of PCGCv1.
    def run(
            self,
            pcfile: Union[str, Path],
            src_dir: Union[str, Path],
            nor_dir: Union[str, Path],
            exp_dir: Union[str, Path],
            scale: int,
            color: bool = False,
            resolution: int = None,
            gpu_queue: BaseProxy = None
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
        scale : `int`
            The maximum length of the ``pcfile`` among x, y, and z axes.
            Used as an encoding parameter in several PCC algorithms.
        color : `bool`, optional
            True for ``pcfile`` containing color, false otherwise. 
            Defaults to false.
        resolution : `int`, optional
            Maximum NN distance of the ``pcfile``. Only used for 
            evaluation. If the resolution is not specified, it will be 
            calculated on the fly. Defaults to None.
        gpu_queue : `BaseProxy`, optional
            A multiprocessing Manager.Queue() object. The queue stores 
            the GPU device IDs get from GPUtil.getAvailable(). Must be 
            assigned if running a PCC algorithm using GPUs. Defaults to 
            None.
        """
        self._pc_scale = scale
        self._color = color
        
        in_pcfile, nor_pcfile, bin_file, out_pcfile, evl_log = (
            self._set_filepath(pcfile, src_dir, nor_dir, exp_dir)
        )
        
        enc_cmd = self.make_encode_cmd(in_pcfile, bin_file)
        dec_cmd = self.make_decode_cmd(bin_file, out_pcfile)

        # use mutable variable
        enc_time = [-1.0]
        dec_time = [-1.0]

        if self._run_command(enc_cmd, enc_time, gpu_queue):
            pass
        else:
            # failed on running encoding/decoding commands
            # skip the evaluation and logging phase
            return
        if self._run_command(dec_cmd, dec_time, gpu_queue):
            pass
        else:
            # failed on running encoding/decoding commands
            # skip the evaluation and logging phase
            return

        # grab all the encoded binary files with same filename, but 
        # different suffix
        bin_files = glob_file(
            Path(bin_file).parent, Path(bin_file).stem+'*', fullpath=True
        )
        VIMetrics = ViewIndependentMetrics()
        ret = VIMetrics.evaluate(
            nor_pcfile,
            out_pcfile,
            color,
            resolution,
            enc_time[0],
            dec_time[0],
            bin_files
        )
        with open(evl_log, 'w') as f:
            f.write(ret)