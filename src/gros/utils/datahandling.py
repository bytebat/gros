import math
import os
import numpy as np
import pandas as pd
import rerun as rr
import subprocess

from gros.utils import log, transforms as tf


logger = log.init_logger(__name__)
DATA_COLUMNS = ["tau", "t", "x", "y", "z"]


class SpaceTimeData:
    """
    Class for wrapping spacetime data points.
    """

    def __init__(
        self, trajectory, rs, conversion=tf.CoordinateConversion.spherical_to_cartesian
    ):
        """
        Initialize dataset of trajectory points.
        Arguments:
        rs -- Schwarzschild radius of center mass [m]
        """
        if not isinstance(trajectory, np.ndarray):
            raise ValueError("dataset must be numpy ndarray!")
        if trajectory.shape != (len(trajectory), 5):
            raise ValueError("dataset shape needs to be (N,5)!")

        self.rs = rs
        self.max_num_anim_frames = 100

        if trajectory.any():
            self.df = pd.DataFrame(trajectory, columns=DATA_COLUMNS)
            if conversion is tf.CoordinateConversion.spherical_to_cartesian:
                for traj_point in trajectory:
                    (
                        traj_point[2],
                        traj_point[3],
                        traj_point[4],
                    ) = tf.spherical_to_cartesian(
                        r=traj_point[2], theta=traj_point[3], phi=traj_point[4]
                    )

    def size(self):
        """
        Returns number of datapoints.
        """
        return len(self.df.index)

    def plot(self, attractor_radius=0, animation_step_size=0):
        """
        Visualizes the provided trajectory data using Rerun.

        Arguments:
            attractor_radius {int} -- Adds an additional sphere with given radius [m] to the visualization (default: 0)
            animation_step_size {int} -- step size [s] > 0 will create frames at that interval (default: 0)
        """
        rr.init("gros", spawn=False)

        data = self.df
        x = data["x"].values
        y = data["y"].values
        z = data["z"].values

        # Log trajectory as 3D line strip
        trajectory_points = np.column_stack((x, y, z))
        rr.log(
            "world/trajectory",
            rr.LineStrips3D(
                strips=[trajectory_points],
            ),
        )

        # Log singularity
        rr.log(
            "world/singularity",
            rr.Points3D(
                [[0, 0, 0]],
                radii=rr.Radius.ui_points(5.0),
                colors=[138, 43, 226],  # darkviolet
            ),
        )

        self._log_sphere(radius=self.rs, name="black_hole", color=(138, 43, 226), opacity=0.2)

        if attractor_radius > 0:
            self._log_sphere(radius=attractor_radius, name="attractor", color=(255, 255, 0), opacity=0.1)

        if animation_step_size > 0:
            self._add_rerun_animation_frames(animation_step_size)

        # determine host IP in case of WSL setup
        if "WSL_DISTRO_NAME" in os.environ:
            host_ip = subprocess.check_output(
                "ip route | awk '/default/ {print $3}'",
                shell=True
            ).decode().strip()

            rr.connect_grpc(f"rerun+http://{host_ip}:9876/proxy")
        else:
            rr.spawn()


    def _log_sphere(self, radius, name, color, opacity):
        """Log a sphere mesh to Rerun.
        
        Arguments:
            radius -- sphere radius
            name -- entity name
            color -- RGB tuple (0-255)
            opacity -- opacity value (0.0-1.0)
        """
        sph_theta = np.linspace(0, 2 * np.pi, 16)
        sph_phi = np.linspace(0, np.pi, 16)
        sph_theta, sph_phi = np.meshgrid(sph_phi, sph_theta)

        sph_x, sph_y, sph_z = tf.spherical_to_cartesian(radius, sph_theta, sph_phi)

        # Flatten for point cloud representation
        points = np.column_stack((sph_x.flatten(), sph_y.flatten(), sph_z.flatten()))
        
        rr.log(
            f"world/{name}",
            rr.Points3D(
                points,
                radii=rr.Radius.ui_points(2.0),
                colors=[*color],
            ),
        )

    def _add_rerun_animation_frames(self, anim_step_size):
        """Log animation frames at specified time intervals using Rerun.

        Arguments:
            anim_step_size -- animation step size [s]
        """
        if anim_step_size <= 0:
            return

        data = self.df
        frame_step_size = math.ceil(anim_step_size / data["tau"].max() * self.size())

        if frame_step_size > self.max_num_anim_frames:
            frame_step_size = self.max_num_anim_frames
            logger.warning(
                f"animation_step_size is too large. "
                f"Maximum number of animation frames will be limited to {self.max_num_anim_frames}."
            )

        # Log particle position at each frame
        for k in range(1, self.size(), frame_step_size):
            current_tau = data["tau"][k]
            current_t = data["t"][k]
            time_dilation = current_t / current_tau if current_tau != 0 else 0
            time_diff = abs(current_t - current_tau)

            rr.set_time("tau", duration=current_tau)
            rr.log(
                "world/particle",
                rr.Points3D(
                    [[data["x"][k], data["y"][k], data["z"][k]]],
                    radii=rr.Radius.ui_points(6.0),
                    colors=[255, 0, 0],  # red
                    labels=[f"tau={current_tau}s", f"t={current_t}s", f"γ={time_dilation:.6f}", f"Δt={time_diff}s"]
                ),
            )
