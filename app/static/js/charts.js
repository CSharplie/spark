/* Initializes/updates ECharts instances found in HTMX-swapped fragments.
   See docs/06-dashboard-views.md and docs/07-project-structure.md. */
(function () {
  function initCharts(root) {
    root.querySelectorAll(".echart[data-option]").forEach(function (el) {
      if (el.__echartsInstance) {
        el.__echartsInstance.dispose();
      }
      var option = JSON.parse(el.getAttribute("data-option"));
      var chart = echarts.init(el);
      chart.setOption(option);
      el.__echartsInstance = chart;
    });
  }

  function resizeCharts() {
    document.querySelectorAll(".echart").forEach(function (el) {
      if (el.__echartsInstance) {
        el.__echartsInstance.resize();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initCharts(document);
  });
  document.body.addEventListener("htmx:afterSwap", function (evt) {
    initCharts(evt.detail.target);
  });
  window.addEventListener("resize", resizeCharts);
})();
