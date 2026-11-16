// Load the page again from the server. An expired sign-in can only be renewed this way: the login
// redirect makes a background request fail, so retrying that request cannot work. Tests mock this.
export function reloadPage() {
  window.location.reload();
}
