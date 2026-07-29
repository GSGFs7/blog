// CF's bot fighter
window.cloudflareJsdOnload = function () {
  window.cloudflare.jsd.executeOnce({
    callback: function () {
      delete window.cloudflareJsdOnload;
    },
  });
}
