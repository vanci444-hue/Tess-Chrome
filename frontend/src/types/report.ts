import type { CapturedField, Issue, SourceRef } from "./api";
export interface OptionView {
  capture_id: string;
  validity: string;
  fields: CapturedField[];
  issues: Issue[];
  preference: string | null;
  captured_at: string;
}
export interface FinanceSolution {
  term_months: number;
  down_payment_fen: number;
  principal_fen: number;
  monthly_payment_fen: number;
  last_payment_fen: number;
  total_installments_fen: number;
  financing_cost_fen: number;
  upfront_fees_fen: number;
  financed_fees_fen: number;
  method: string;
  source_kind: string;
}
export interface FinanceView {
  capture_id: string;
  product_id: string;
  state: string;
  solutions: FinanceSolution[];
  constraints: {
    monthly_cap_fen?: number;
    down_payment_min_fen?: number;
    down_payment_max_fen?: number;
  };
  price_fen: number;
  unmet_constraints: string[];
  note: string;
}
export interface EnergyView {
  assumptions: {
    annual_km: number;
    years: number;
    kwh_per_100km: number;
    electricity_yuan_per_kwh: number;
    liters_per_100km: number;
    fuel_yuan_per_liter: number;
    source: string;
  };
  annual_electric_fen: number;
  annual_fuel_fen: number;
  series: {
    year: number;
    electric_fen: number;
    fuel_fen: number;
    saving_fen: number;
  }[];
  scope: string;
  label: string;
}
export interface StationView {
  number: number;
  id: string;
  name: string;
  center_distance_m: number;
  driving_distance_m: number | null;
  driving_duration_seconds: number | null;
  distance_basis: string;
  route_status: string;
}
export interface ChargingView {
  state: string;
  region: string;
  city: string | null;
  radius_m: number;
  stations: StationView[];
  map_asset_id: string | null;
  map_status: string;
  external_search?: { label: string; url: string };
  warnings: string[];
  observed_at: string;
}
export interface FamilyView {
  topic: string;
  entries: { title: string; text: string; url: string; reviewed_at: string }[];
  state: string;
}
export interface SectionProps {
  sources: SourceRef[];
  status: string;
}
