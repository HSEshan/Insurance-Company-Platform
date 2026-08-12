import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  Select,
} from "../../components/ui";
import { useAuthStore } from "../../stores/authStore";
import type {
  CustomerListItem,
  Envelope,
  Meta,
  PolicyType,
  Quote,
} from "../../types";

type Step = 1 | 2 | 3 | 4;

const defaultAuto = {
  state: "OH",
  driver_age: 35,
  vehicle_type: "sedan",
  vehicle_year: 2020,
  coverage_type: "full_coverage",
  annual_mileage: 12000,
  collision_deductible: "500",
  dui_count: 0,
  speeding_violations: 0,
  at_fault_claims_3yr: 0,
  credit_score: 720,
  has_existing_home_policy: false,
  anti_theft_device: false,
};

const defaultAutoDetails = {
  vin: "1HGCM82633A004352",
  make: "Honda",
  model: "Accord",
  year: 2020,
  vehicle_type: "sedan",
  primary_use: "commute",
  annual_mileage: 12000,
  garaging_zip: "44101",
  coverage_type: "full_coverage",
  liability_limit: "100000",
  collision_deductible: "500",
  comprehensive_deductible: "500",
  uninsured_motorist: false,
  roadside_assistance: false,
  rental_reimbursement: false,
};

const defaultHome = {
  state: "OH",
  dwelling_coverage: "350000",
  year_built: 2005,
  roof_year: 2018,
  construction_type: "frame",
  deductible: "1000",
  claims_3yr: 0,
  in_flood_zone: false,
  has_flood_rider: false,
  has_security_system: true,
  credit_score: 720,
};

const defaultHomeDetails = {
  property_address_line1: "100 Main St",
  property_address_line2: "",
  city: "Cleveland",
  state: "OH",
  zip: "44101",
  year_built: 2005,
  square_footage: 1800,
  construction_type: "frame",
  roof_type: "shingle",
  roof_year: 2018,
  home_value: "350000",
  dwelling_coverage: "350000",
  personal_property_coverage: "175000",
  liability_coverage: "300000",
  deductible: "1000",
  flood_coverage: false,
  earthquake_coverage: false,
  home_business_coverage: false,
};

const defaultLife = {
  age: 40,
  coverage_amount: "250000",
  life_type: "term",
  term_years: 20,
  is_female: false,
  tobacco_user: false,
  health_class: "standard",
};

const defaultLifeDetails = {
  coverage_amount: "250000",
  policy_term_years: 20,
  life_type: "term",
  tobacco_user: false,
  health_class: "standard",
  premium_mode: "level",
  beneficiaries: [
    {
      full_name: "Jordan Lee",
      relationship: "spouse",
      allocation_pct: "100",
      is_contingent: false,
    },
  ],
};

export function QuoteWizardPage() {
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isStaff = role === "agent" || role === "manager" || role === "super_admin";

  const [step, setStep] = useState<Step>(1);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [policyType, setPolicyType] = useState<PolicyType>("auto");
  const [customerId, setCustomerId] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [notes, setNotes] = useState("");

  const [autoRating, setAutoRating] = useState(defaultAuto);
  const [autoDetails, setAutoDetails] = useState(defaultAutoDetails);
  const [homeRating, setHomeRating] = useState(defaultHome);
  const [homeDetails, setHomeDetails] = useState(defaultHomeDetails);
  const [lifeRating, setLifeRating] = useState(defaultLife);
  const [lifeDetails, setLifeDetails] = useState(defaultLifeDetails);

  const { data: customers } = useQuery({
    queryKey: ["customers", { forWizard: true }],
    enabled: isStaff,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<Envelope<CustomerListItem[]>>("/customers", {
        params: { page: 1, per_page: 100 },
      });
      return { items: res.data.data ?? [], meta: res.data.meta ?? (null as Meta | null) };
    },
  });

  const stepLabel = useMemo(
    () =>
      ({
        1: "Basics",
        2: "Rating inputs",
        3: "Policy details",
        4: "Review",
      })[step],
    [step],
  );

  async function handleSubmit() {
    setError(null);
    if (isStaff && !customerId) {
      setError("Select a customer for this quote.");
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        policy_type: policyType,
        effective_date: effectiveDate,
        notes: notes || null,
        customer_id: isStaff ? customerId : null,
      };
      if (policyType === "auto") {
        body.auto_rating = {
          ...autoRating,
          collision_deductible: autoRating.collision_deductible,
        };
        body.auto_details = { ...autoDetails };
      } else if (policyType === "home") {
        body.home_rating = { ...homeRating };
        body.home_details = {
          ...homeDetails,
          property_address_line2: homeDetails.property_address_line2 || null,
        };
      } else {
        body.life_rating = { ...lifeRating };
        body.life_details = { ...lifeDetails };
      }

      const res = await api.post<Envelope<Quote>>("/quotes", body);
      const quote = res.data.data;
      if (!quote) throw new Error("No quote returned");
      navigate(`/quotes/${quote.id}`);
    } catch (err) {
      setError(getErrorMessage(err, "Could not create quote."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <p className="text-sm text-slate-500">
          <Link to="/quotes" className="text-indigo-600 hover:underline">
            Quotes
          </Link>{" "}
          / New
        </p>
        <h2 className="mt-1 text-2xl font-bold text-slate-800">New quote</h2>
        <p className="mt-1 text-sm text-slate-500">
          Step {step} of 4 — {stepLabel}
        </p>
      </div>

      {error && <Alert message={error} />}

      <Card className="space-y-4">
        {step === 1 && (
          <>
            <Field label="Line of business" htmlFor="policy_type">
              <Select
                id="policy_type"
                value={policyType}
                onChange={(e) => setPolicyType(e.target.value as PolicyType)}
              >
                <option value="auto">Auto</option>
                <option value="home">Home</option>
                <option value="life">Life</option>
              </Select>
            </Field>
            {isStaff && (
              <Field label="Customer" htmlFor="customer_id">
                <Select
                  id="customer_id"
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                >
                  <option value="">Select customer…</option>
                  {customers?.items.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.first_name} {c.last_name} ({c.email})
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="Effective date" htmlFor="effective_date">
              <Input
                id="effective_date"
                type="date"
                value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)}
              />
            </Field>
            <Field label="Notes (optional)" htmlFor="notes">
              <Input
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </Field>
          </>
        )}

        {step === 2 && policyType === "auto" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["state", "State"],
                ["driver_age", "Driver age"],
                ["vehicle_year", "Vehicle year"],
                ["annual_mileage", "Annual mileage"],
                ["collision_deductible", "Collision deductible"],
                ["credit_score", "Credit score"],
                ["dui_count", "DUI count"],
                ["speeding_violations", "Speeding violations"],
                ["at_fault_claims_3yr", "At-fault claims (3yr)"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} htmlFor={key}>
                <Input
                  id={key}
                  value={String(autoRating[key])}
                  onChange={(e) =>
                    setAutoRating((s) => ({
                      ...s,
                      [key]:
                        key === "state" || key === "collision_deductible"
                          ? e.target.value
                          : Number(e.target.value),
                    }))
                  }
                />
              </Field>
            ))}
            <Field label="Vehicle type" htmlFor="vehicle_type">
              <Select
                id="vehicle_type"
                value={autoRating.vehicle_type}
                onChange={(e) =>
                  setAutoRating((s) => ({ ...s, vehicle_type: e.target.value }))
                }
              >
                <option value="sedan">Sedan</option>
                <option value="suv">SUV</option>
                <option value="truck">Truck</option>
                <option value="motorcycle">Motorcycle</option>
              </Select>
            </Field>
            <Field label="Coverage" htmlFor="coverage_type">
              <Select
                id="coverage_type"
                value={autoRating.coverage_type}
                onChange={(e) =>
                  setAutoRating((s) => ({ ...s, coverage_type: e.target.value }))
                }
              >
                <option value="liability_only">Liability only</option>
                <option value="comprehensive">Comprehensive</option>
                <option value="collision">Collision</option>
                <option value="full_coverage">Full coverage</option>
              </Select>
            </Field>
          </div>
        )}

        {step === 2 && policyType === "home" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["state", "State"],
                ["dwelling_coverage", "Dwelling coverage"],
                ["year_built", "Year built"],
                ["roof_year", "Roof year"],
                ["deductible", "Deductible"],
                ["claims_3yr", "Claims (3yr)"],
                ["credit_score", "Credit score"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} htmlFor={key}>
                <Input
                  id={key}
                  value={String(homeRating[key])}
                  onChange={(e) =>
                    setHomeRating((s) => ({
                      ...s,
                      [key]:
                        key === "state" ||
                        key === "dwelling_coverage" ||
                        key === "deductible"
                          ? e.target.value
                          : Number(e.target.value),
                    }))
                  }
                />
              </Field>
            ))}
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={homeRating.in_flood_zone}
                onChange={(e) =>
                  setHomeRating((s) => ({ ...s, in_flood_zone: e.target.checked }))
                }
              />
              In flood zone
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={homeRating.has_flood_rider}
                onChange={(e) =>
                  setHomeRating((s) => ({
                    ...s,
                    has_flood_rider: e.target.checked,
                  }))
                }
              />
              Has flood rider
            </label>
          </div>
        )}

        {step === 2 && policyType === "life" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["age", "Age"],
                ["coverage_amount", "Coverage amount"],
                ["term_years", "Term years"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} htmlFor={key}>
                <Input
                  id={key}
                  value={String(lifeRating[key] ?? "")}
                  onChange={(e) =>
                    setLifeRating((s) => ({
                      ...s,
                      [key]:
                        key === "coverage_amount"
                          ? e.target.value
                          : Number(e.target.value),
                    }))
                  }
                />
              </Field>
            ))}
            <Field label="Life type" htmlFor="life_type">
              <Select
                id="life_type"
                value={lifeRating.life_type}
                onChange={(e) =>
                  setLifeRating((s) => ({ ...s, life_type: e.target.value }))
                }
              >
                <option value="term">Term</option>
                <option value="whole">Whole</option>
                <option value="universal">Universal</option>
              </Select>
            </Field>
            <Field label="Health class" htmlFor="health_class">
              <Select
                id="health_class"
                value={lifeRating.health_class}
                onChange={(e) =>
                  setLifeRating((s) => ({ ...s, health_class: e.target.value }))
                }
              >
                <option value="preferred_plus">Preferred plus</option>
                <option value="preferred">Preferred</option>
                <option value="standard_plus">Standard plus</option>
                <option value="standard">Standard</option>
                <option value="substandard">Substandard</option>
              </Select>
            </Field>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={lifeRating.tobacco_user}
                onChange={(e) =>
                  setLifeRating((s) => ({ ...s, tobacco_user: e.target.checked }))
                }
              />
              Tobacco user
            </label>
          </div>
        )}

        {step === 3 && policyType === "auto" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["vin", "VIN"],
                ["make", "Make"],
                ["model", "Model"],
                ["year", "Year"],
                ["garaging_zip", "Garaging ZIP"],
                ["annual_mileage", "Annual mileage"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} htmlFor={`d_${key}`}>
                <Input
                  id={`d_${key}`}
                  value={String(autoDetails[key])}
                  onChange={(e) =>
                    setAutoDetails((s) => ({
                      ...s,
                      [key]:
                        key === "year" || key === "annual_mileage"
                          ? Number(e.target.value)
                          : e.target.value,
                    }))
                  }
                />
              </Field>
            ))}
          </div>
        )}

        {step === 3 && policyType === "home" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["property_address_line1", "Address"],
                ["city", "City"],
                ["state", "State"],
                ["zip", "ZIP"],
                ["dwelling_coverage", "Dwelling coverage"],
                ["deductible", "Deductible"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} htmlFor={`hd_${key}`}>
                <Input
                  id={`hd_${key}`}
                  value={String(homeDetails[key])}
                  onChange={(e) =>
                    setHomeDetails((s) => ({ ...s, [key]: e.target.value }))
                  }
                />
              </Field>
            ))}
          </div>
        )}

        {step === 3 && policyType === "life" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Coverage amount" htmlFor="ld_coverage">
              <Input
                id="ld_coverage"
                value={lifeDetails.coverage_amount}
                onChange={(e) =>
                  setLifeDetails((s) => ({
                    ...s,
                    coverage_amount: e.target.value,
                  }))
                }
              />
            </Field>
            <Field label="Primary beneficiary" htmlFor="ld_ben">
              <Input
                id="ld_ben"
                value={lifeDetails.beneficiaries[0]?.full_name ?? ""}
                onChange={(e) =>
                  setLifeDetails((s) => ({
                    ...s,
                    beneficiaries: [
                      {
                        ...s.beneficiaries[0],
                        full_name: e.target.value,
                        relationship: "spouse",
                        allocation_pct: "100",
                        is_contingent: false,
                      },
                    ],
                  }))
                }
              />
            </Field>
          </div>
        )}

        {step === 4 && (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-slate-500">Type</dt>
              <dd className="capitalize text-slate-800">{policyType}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Effective</dt>
              <dd className="text-slate-800">{effectiveDate}</dd>
            </div>
            {isStaff && (
              <div className="flex justify-between">
                <dt className="text-slate-500">Customer</dt>
                <dd className="font-mono text-xs text-slate-800">{customerId}</dd>
              </div>
            )}
            <p className="pt-2 text-slate-500">
              Creating the quote will run the rate engine and save a draft (or
              rejected if hard-declined).
            </p>
          </dl>
        )}

        <div className="flex justify-between pt-2">
          <Button
            variant="secondary"
            disabled={step === 1 || submitting}
            onClick={() => setStep((s) => (s > 1 ? ((s - 1) as Step) : s))}
          >
            Back
          </Button>
          {step < 4 ? (
            <Button onClick={() => setStep((s) => (s + 1) as Step)}>Next</Button>
          ) : (
            <Button loading={submitting} onClick={handleSubmit}>
              Create quote
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
