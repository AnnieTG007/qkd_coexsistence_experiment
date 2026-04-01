import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtGui import QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.lines import Line2D


@dataclass
class PlotStyleConfig:
    """
    绘图风格配置
    """
    background_color: str = "#0b1020"      # 整体背景
    axes_color: str = "#121a2b"            # 坐标区背景
    grid_color: str = "#2b3b5a"
    spine_color: str = "#62708a"
    text_color: str = "#e8eefc"

    classical_color: str = "#3fb7ff"       # 经典信道：蓝色
    quantum_color: str = "#ff4fa3"         # 量子信道：粉紫色

    title_fontsize: int = 18
    label_fontsize: int = 13
    tick_fontsize: int = 11
    legend_fontsize: int = 11

    classical_arrow_height: float = 0.88
    quantum_arrow_height: float = 0.48

    classical_arrow_width: float = 0.0     # annotate箭头本身不用这个参数，仅保留给后续扩展
    quantum_arrow_width: float = 0.0

    arrow_linewidth: float = 2.2
    glow_linewidth: float = 7.5            # 用于制造“发光”边缘感
    marker_size: float = 70

    margin_ratio: float = 0.04             # 横轴左右留白比例


class ChannelDistributionCanvas(FigureCanvas):
    """
    承载 matplotlib 图像的画布
    """

    def __init__(
        self,
        classical_channels: np.ndarray,
        quantum_channels: np.ndarray,
        style: Optional[PlotStyleConfig] = None,
        parent=None
    ):
        self.style = style if style is not None else PlotStyleConfig()

        self._validate_input(classical_channels, quantum_channels)

        self.classical_channels = np.sort(np.asarray(classical_channels, dtype=float).ravel())
        self.quantum_channels = np.sort(np.asarray(quantum_channels, dtype=float).ravel())

        self.figure = Figure(figsize=(12, 6.5), dpi=120, facecolor=self.style.background_color)
        super().__init__(self.figure)
        self.setParent(parent)

        self.ax = self.figure.add_subplot(111)
        self._setup_axes()
        self._plot_channels()
        self.figure.tight_layout(pad=2.0)

    @staticmethod
    def _validate_input(classical_channels: np.ndarray, quantum_channels: np.ndarray) -> None:
        """
        校验输入是否合法
        """
        if not isinstance(classical_channels, np.ndarray):
            raise TypeError("classical_channels must be a numpy.ndarray")
        if not isinstance(quantum_channels, np.ndarray):
            raise TypeError("quantum_channels must be a numpy.ndarray")

        if classical_channels.size == 0 and quantum_channels.size == 0:
            raise ValueError("At least one of classical_channels or quantum_channels must be non-empty.")

        if classical_channels.ndim > 2 or quantum_channels.ndim > 2:
            raise ValueError("Input arrays should be 1D or flattenable arrays of center frequencies.")

        if classical_channels.size > 0 and not np.issubdtype(classical_channels.dtype, np.number):
            raise TypeError("classical_channels must contain numeric values.")
        if quantum_channels.size > 0 and not np.issubdtype(quantum_channels.dtype, np.number):
            raise TypeError("quantum_channels must contain numeric values.")

    def _setup_axes(self) -> None:
        """
        设置深色科技风坐标系
        """
        s = self.style
        ax = self.ax

        ax.set_facecolor(s.axes_color)

        for spine in ax.spines.values():
            spine.set_color(s.spine_color)
            spine.set_linewidth(1.2)

        ax.tick_params(axis="x", colors=s.text_color, labelsize=s.tick_fontsize)
        ax.tick_params(axis="y", left=False, labelleft=False)

        ax.grid(True, axis="x", color=s.grid_color, linestyle="--", linewidth=0.8, alpha=0.45)
        ax.grid(True, axis="y", color=s.grid_color, linestyle=":", linewidth=0.5, alpha=0.18)

        ax.set_title(
            "Classical and Quantum Channel Distribution",
            color=s.text_color,
            fontsize=s.title_fontsize,
            fontweight="bold",
            pad=16
        )
        ax.set_xlabel(
            "Frequency (THz)",
            color=s.text_color,
            fontsize=s.label_fontsize,
            labelpad=12
        )

        ax.set_ylim(0.0, 1.15)

    def _compute_xlim(self) -> tuple[float, float]:
        """
        根据输入信道自动计算横轴范围
        """
        all_channels = []
        if self.classical_channels.size > 0:
            all_channels.append(self.classical_channels)
        if self.quantum_channels.size > 0:
            all_channels.append(self.quantum_channels)

        all_channels = np.concatenate(all_channels)
        all_channels_thz = all_channels / 1e12

        f_min = np.min(all_channels_thz)
        f_max = np.max(all_channels_thz)

        if np.isclose(f_min, f_max):
            delta = 0.2
            return f_min - delta, f_max + delta

        span = f_max - f_min
        margin = max(span * self.style.margin_ratio, 0.05)
        return f_min - margin, f_max + margin

    def _draw_single_arrow(
        self,
        x_thz: float,
        y_top: float,
        color: str,
        label_text: Optional[str] = None
    ) -> None:
        """
        绘制单个竖直箭头，并带一点“发光”效果
        """
        s = self.style
        ax = self.ax

        # 先画一层更粗、更透明的“辉光”
        ax.annotate(
            "",
            xy=(x_thz, y_top),
            xytext=(x_thz, 0.08),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=s.glow_linewidth,
                alpha=0.12,
                shrinkA=0,
                shrinkB=0,
                mutation_scale=20
            ),
            zorder=2
        )

        # 再画主箭头
        ax.annotate(
            "",
            xy=(x_thz, y_top),
            xytext=(x_thz, 0.08),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=s.arrow_linewidth,
                alpha=0.98,
                shrinkA=0,
                shrinkB=0,
                mutation_scale=18
            ),
            zorder=4
        )

        # 箭头顶端点缀
        ax.scatter(
            [x_thz],
            [y_top],
            s=s.marker_size,
            color=color,
            alpha=0.15,
            zorder=3
        )
        ax.scatter(
            [x_thz],
            [y_top],
            s=s.marker_size * 0.28,
            color=color,
            alpha=0.95,
            zorder=5
        )

        # 可选：在箭头附近标频率
        if label_text is not None:
            ax.text(
                x_thz,
                y_top + 0.035,
                label_text,
                color=s.text_color,
                fontsize=9,
                ha="center",
                va="bottom",
                alpha=0.9
            )

    def _plot_channels(self) -> None:
        """
        绘制经典/量子信道
        """
        s = self.style
        ax = self.ax

        x_left, x_right = self._compute_xlim()
        ax.set_xlim(x_left, x_right)

        # 背景中的轻微水平参考线，增强视觉层次
        ax.axhline(s.classical_arrow_height, color=s.classical_color, alpha=0.08, lw=1.2, ls="--", zorder=1)
        ax.axhline(s.quantum_arrow_height, color=s.quantum_color, alpha=0.08, lw=1.2, ls="--", zorder=1)

        # 经典信道
        for freq in self.classical_channels:
            x_thz = freq / 1e12
            self._draw_single_arrow(
                x_thz=x_thz,
                y_top=s.classical_arrow_height,
                color=s.classical_color
            )

        # 量子信道
        for freq in self.quantum_channels:
            x_thz = freq / 1e12
            self._draw_single_arrow(
                x_thz=x_thz,
                y_top=s.quantum_arrow_height,
                color=s.quantum_color
            )

        # 图例
        legend_handles = [
            Line2D(
                [0], [0],
                color=s.classical_color,
                lw=2.5,
                marker="^",
                markersize=8,
                label="Classical Channel"
            ),
            Line2D(
                [0], [0],
                color=s.quantum_color,
                lw=2.5,
                marker="^",
                markersize=8,
                label="Quantum Channel"
            ),
        ]

        legend = ax.legend(
            handles=legend_handles,
            loc="upper right",
            frameon=True,
            fontsize=s.legend_fontsize,
            facecolor="#172136",
            edgecolor="#4d5d7a",
            labelcolor=s.text_color,
            borderpad=0.8
        )
        for text in legend.get_texts():
            text.set_color(s.text_color)


class ChannelDistributionWindow(QMainWindow):
    """
    主窗口
    """

    def __init__(
        self,
        classical_channels: np.ndarray,
        quantum_channels: np.ndarray,
        window_title: str = "Channel Distribution Viewer",
        style: Optional[PlotStyleConfig] = None
    ):
        super().__init__()

        self.style = style if style is not None else PlotStyleConfig()
        self.setWindowTitle(window_title)
        self.resize(1280, 760)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(14, 14, 14, 14)

        self.canvas = ChannelDistributionCanvas(
            classical_channels=classical_channels,
            quantum_channels=quantum_channels,
            style=self.style
        )
        layout.addWidget(self.canvas)

        self._apply_qt_style()

    def _apply_qt_style(self) -> None:
        """
        Qt窗口本身的深色风格
        """
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b1020;
            }
            QWidget {
                background-color: #0b1020;
                color: #e8eefc;
                font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC";
                font-size: 11pt;
            }
        """)


def show_channel_distribution(
    classical_channels: np.ndarray,
    quantum_channels: np.ndarray,
    window_title: str = "Channel Distribution Viewer"
) -> None:
    """
    外部直接调用的展示函数

    Parameters
    ----------
    classical_channels : np.ndarray
        经典信道中心频率数组，单位 Hz
    quantum_channels : np.ndarray
        量子信道中心频率数组，单位 Hz
    window_title : str
        窗口标题
    """
    app = QApplication.instance()
    created_here = False

    if app is None:
        app = QApplication(sys.argv)
        created_here = True

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = ChannelDistributionWindow(
        classical_channels=classical_channels,
        quantum_channels=quantum_channels,
        window_title=window_title
    )
    window.show()

    if created_here:
        sys.exit(app.exec())


if __name__ == "__main__":
    # 示例数据：单位 Hz
    classical = np.array([
        193.10e12, 193.20e12, 193.30e12, 193.40e12,
        193.60e12, 193.70e12
    ])

    quantum = np.array([
        193.5e12
    ])

    show_channel_distribution(
        classical_channels=classical,
        quantum_channels=quantum,
        window_title="QKD Network Channel Distribution"
    )