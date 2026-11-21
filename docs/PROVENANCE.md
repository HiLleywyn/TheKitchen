# Provenance rules

Every stored or reported number carries a `kind`. There are five, ranked by how
hard the claim is to dispute.

| Kind | Means | Example |
| --- | --- | --- |
| `measured` | An instrument reading, with method recorded | hydrometer 1.046 at 80 °F, corrected to 1.0484 |
| `calculated` | Arithmetic on measured inputs | apparent attenuation 78.8% |
| `user_supplied` | The brewer typed it | "kegged", a target volume, an ingredient amount |
| `estimated` | A model or rule of thumb produced it | ABV 5.49%, predicted OG 1.057 |
| `inferred` | Derived from state, not observed | "stable, likely ready to package" |

`Value.recast` may only move down this list. Moving up raises
`ProvenanceError`. A `measured` or `calculated` value must name its method;
constructing one without a method fails.

## The cases that are easy to get wrong

**ABV is never a measurement.** It is computed from two gravities, so it is
`estimated` no matter how precise the gravities were. The method string says
"not measured" so the label survives being copied into a chat message.

**A temperature-corrected hydrometer reading is still `measured`.** The
instrument reading is the evidence; the correction is arithmetic applied to it.
The method records both the raw reading and the temperatures, so the correction
can be audited or redone with a different calibration.

**A predicted OG is `estimated`, a measured OG is `measured`.** They can be the
same number. They are not the same claim. `predict_og` never returns a
measurement.

**Batch status is `inferred` unless the brewer said otherwise.** "Stable, likely
ready to package" includes the word "likely" because the app is guessing from
gravity readings. If the brewer sets a status, it becomes `user_supplied` and
outranks the guess.

**A late first reading is not an original gravity.** If the first gravity
reading came more than 12 hours after the batch started, the summary says so
rather than quietly treating it as OG and computing ABV from it.

**Reference knowledge needs a source.** `add_reference` rejects a note with no
`source_url`. A brewing claim without provenance is a rumour, and this project
exists to avoid those.

## Reading the output

Every value serialises as:

```json
{
  "value": 5.49,
  "unit": "% ABV",
  "kind": "estimated",
  "method": "ABV = 76.08(OG-FG)/(1.775-OG) x FG/0.794; estimated from OG 1.0520 and FG 1.0110, not measured",
  "source": ""
}
```

If a consumer drops `kind`, it is lying about the number. Keep it.
