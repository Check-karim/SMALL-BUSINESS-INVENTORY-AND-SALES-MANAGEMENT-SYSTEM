(function () {
  document.querySelectorAll("[data-nav-toggle]").forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      document.body.classList.toggle("nav-open");
    });
  });

  document.querySelectorAll("[data-confirm]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      if (!window.confirm(button.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });

  var password = document.querySelector("[data-password]");
  var meter = document.querySelector("[data-password-meter]");
  if (password && meter) {
    var paintPassword = function () {
      var count = password.value.length;
      if (!count) {
        meter.textContent = "At least 6 characters.";
      } else if (count < 6) {
        meter.textContent = count + " of 6 characters minimum.";
      } else {
        meter.textContent = count + " characters. Length is fine.";
      }
    };
    password.addEventListener("input", paintPassword);
    paintPassword();
  }

  var form = document.querySelector("[data-lines]");
  var catalogNode = document.getElementById("catalog-data");
  if (!form || !catalogNode) return;

  var catalog = JSON.parse(catalogNode.textContent);
  var byId = {};
  catalog.forEach(function (item) { byId[String(item.id)] = item; });
  var body = form.querySelector("[data-line-body]");
  var grand = form.querySelector("[data-grand]");
  var branchInput = form.querySelector("[name='branch_id']");

  function branchId() {
    return branchInput ? String(branchInput.value || "") : "";
  }

  function money(cents) {
    var sign = cents < 0 ? "-" : "";
    var abs = Math.abs(Math.round(cents));
    var whole = String(Math.floor(abs / 100));
    var frac = String(abs % 100).padStart(2, "0");
    var withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return sign + "$" + withCommas + "." + frac;
  }

  function cents(price) {
    var parts = String(price).split(".");
    var whole = Number(parts[0] || 0);
    var frac = Number((parts[1] || "0").padEnd(2, "0").slice(0, 2));
    return whole * 100 + frac;
  }

  function paintRow(row) {
    var select = row.querySelector("[name='product_id']");
    var qtyInput = row.querySelector("[name='quantity']");
    var product = byId[select.value];
    var avail = row.querySelector("[data-avail]");
    var priceCell = row.querySelector("[data-price]");
    var totalCell = row.querySelector("[data-line-total]");
    if (!product) {
      avail.textContent = "—";
      avail.classList.remove("is-low");
      priceCell.textContent = "—";
      totalCell.textContent = "—";
      totalCell.dataset.cents = "0";
      return;
    }
    var stock = Number((product.stock || {})[branchId()] || 0);
    avail.textContent = stock + " in branch";
    avail.classList.toggle("is-low", stock <= 0);
    var unit = cents(product.price);
    var qty = Math.max(0, Number(qtyInput.value || 0));
    priceCell.textContent = money(unit);
    var line = unit * qty;
    totalCell.textContent = money(line);
    totalCell.dataset.cents = String(line);
  }

  function paintAll() {
    var sum = 0;
    body.querySelectorAll("[data-line]").forEach(function (row) {
      paintRow(row);
      sum += Number(row.querySelector("[data-line-total]").dataset.cents || 0);
    });
    if (grand) grand.textContent = money(sum);
  }

  body.addEventListener("change", paintAll);
  body.addEventListener("input", paintAll);
  if (branchInput) branchInput.addEventListener("change", paintAll);

  var add = form.querySelector("[data-add-line]");
  if (add) {
    add.addEventListener("click", function () {
      var rows = body.querySelectorAll("[data-line]");
      var clone = rows[rows.length - 1].cloneNode(true);
      var select = clone.querySelector("select");
      if (select) select.selectedIndex = 0;
      var qty = clone.querySelector("[name='quantity']");
      if (qty) qty.value = "1";
      body.appendChild(clone);
      paintAll();
    });
  }

  body.addEventListener("click", function (event) {
    var button = event.target.closest("[data-remove-line]");
    if (!button) return;
    var rows = body.querySelectorAll("[data-line]");
    if (rows.length === 1) {
      var select = rows[0].querySelector("select");
      if (select) select.selectedIndex = 0;
      var qty = rows[0].querySelector("[name='quantity']");
      if (qty) qty.value = "1";
      paintAll();
      return;
    }
    button.closest("[data-line]").remove();
    paintAll();
  });

  paintAll();
})();
