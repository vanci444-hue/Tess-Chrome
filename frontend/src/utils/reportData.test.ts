import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  numericField,
  chartSeries,
  financeRows,
  safeMapUrl,
} from "./reportData.ts";
import type { CapturedField } from "../types/api.ts";
import type { ChargingView, EnergyView, FinanceView } from "../types/report.ts";
test("missing numbers remain null rather than chart zero; amounts stay in fen", () => {
  assert.equal(numericField([], "range_cltc"), null);
  const fields = [{ key: "vehicle_price", value: 32150000 }] as CapturedField[];
  assert.equal(numericField(fields, "vehicle_price"), 32150000);
});
test("chart rows use the same source amounts, reject missing points", () => {
  const data = {
    series: [
      { year: 1, electric_fen: 360000, fuel_fen: 1280000, saving_fen: 920000 },
      { year: 2, electric_fen: null, fuel_fen: 2560000, saving_fen: null },
    ],
  } as unknown as EnergyView;
  assert.deepEqual(chartSeries(data), [data.series[0]]);
  const finance = {
    solutions: [
      {
        monthly_payment_fen: 402667,
        down_payment_fen: 8000000,
        term_months: 60,
      },
    ],
  } as FinanceView;
  assert.equal(financeRows(finance)[0].monthly_payment_fen, 402667);
});
test("only confirmed-region Amap search navigation is exposed, no API key query", () => {
  const charging = {
    region: "望京",
    external_search: {
      label: "高德",
      url: "https://uri.amap.com/search?keyword=%E6%9C%9B%E4%BA%AC&city=北京&view=map",
    },
  } as ChargingView;
  assert.ok(safeMapUrl(charging));
  assert.equal(safeMapUrl({ ...charging, region: "" }), null);
  assert.equal(
    safeMapUrl({
      ...charging,
      external_search: {
        label: "bad",
        url: charging.external_search!.url + "&key=secret",
      },
    }),
    null,
  );
  assert.equal(
    safeMapUrl({
      ...charging,
      external_search: {
        label: "bad",
        url: "https://example.com/search?keyword=望京",
      },
    }),
    null,
  );
});
