// T-R02 — Canvas sparkline extracted from panel.js.
import { SPARK_MAX_POINTS } from "./constants.js";

export class Sparkline {
  constructor(canvasId, color) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.color = color;
    this.data = [];
  }

  push(v) {
    if (!this.canvas) return;
    this.data.push(Number(v) || 0);
    if (this.data.length > SPARK_MAX_POINTS) this.data.shift();
    this.draw();
  }

  draw() {
    const { width, height } = this.canvas;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, width, height);
    if (this.data.length < 2) return;
    const min = Math.min(...this.data);
    const max = Math.max(...this.data);
    const range = max - min || 1;
    ctx.beginPath();
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 2;
    this.data.forEach((val, i) => {
      const x = (i / (SPARK_MAX_POINTS - 1)) * width;
      const y = height - ((val - min) / range) * (height - 2) - 1;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
}
