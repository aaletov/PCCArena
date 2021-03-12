import time
import logging
import subprocess as sp
from multiprocessing import Pool
from typing import Callable, Iterable

import GPUtil
from tqdm import tqdm

logger = logging.getLogger(__name__)

def timer(func: Callable, *args, **kwargs) -> float:
    """Calculate function execution time.

    Parameters
    ----------
    func : `Callable`
        Function to execute.

    Returns
    -------
    `float`
        Execution time in seconds.
    """
    start_time = time.time()
    func(*args, **kwargs)
    end_time = time.time() - start_time
    
    return end_time

def execute_cmd(cmd: list[str], shell: bool = False, cwd: str = None) -> bool:
    """Wrapper for executing a command with subprocess.

    Parameters
    ----------
    cmd : `list[str]`
        Command to execute.
    shell : `bool`, optional
        True to run in shell mode, False otherwise, by default False.
    cwd : `str`, optional
        Specify command working directory, by default None.

    Returns
    -------
    `bool`
        True if successful, False otherwise.
    """
    ret = sp.run(cmd, capture_output=True, shell=shell, cwd=cwd)
    try:
        assert ret.returncode == 0
    except AssertionError:
        logger.info(
            f"The stdout and stderr of executed command: "
            f"{''.join(str(s)+' ' for s in cmd)}"
        )
        print(f"\n {ret.stdout.decode('utf-8')}")
        print(f"\n {ret.stderr.decode('utf-8')}")
        return False
    else:
        return True

def parallel(func: Callable, filelist:Iterable, use_gpu: bool = False) -> None:
    """Parallel processing with multiprocessing.Pool(), works better 
    with functools.partial().
    
    Parameters
    ----------
    func : `Callable`
        The target function for parallel processing.
    filelist : `Iterable`
        The file list to process with the input function.
    use_gpu : `bool`, optional
        True for running NN-based PCC algs., False otherwise. 
        Defaults to False.
    
    Raises
    ------
    `ValueError`
        No available GPU.
    """
    if use_gpu is True:
        # Get the number of available GPUs
        deviceIDs = GPUtil.getAvailable(
            order = 'first',
            limit = 8,
            maxLoad = 0.5,
            maxMemory = 0.2,
            includeNan=False,
            excludeID=[],
            excludeUUID=[]
        )
        process = len(deviceIDs)
        
        if process <= 0:
            logger.error(
                "No available GPU. Check with the threshold parameters "
                "of ``GPUtil.getAvailable()``"
            )
            raise ValueError
    else:
        process = None

    with Pool(process) as pool:
        list(tqdm(pool.imap_unordered(func, filelist), total=len(filelist)))