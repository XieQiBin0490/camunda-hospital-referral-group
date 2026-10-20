# The i\* models as redrawn on 20 October 2026

Both figures were drawn in **piStar 2.1.0** and exported as piStar JSON. The SVG, PNG and PDF here
are rendered straight from the coordinates in those JSON files, so the picture is the picture the
group drew: nothing is re-laid-out, and the JSON beside each figure is the editable source.

| Figure | Editable source | Rendered |
| --- | --- | --- |
| Strategic Dependency | `iStar_SD_pistar.json` | `iStar_SD_final.svg` / `.png` / `.pdf` |
| Strategic Rationale | `iStar_SR_pistar.json` | `iStar_SR_final.svg` / `.png` / `.pdf` |

## What each model contains

| | Strategic Dependency | Strategic Rationale |
| --- | --- | --- |
| Actors | 16, all collapsed (leaf) | 14: 6 opened, 8 external |
| Intentional elements | — | 45 (21 tasks, 13 goals, 11 soft goals) |
| Dependencies | 30 (14 resource, 10 task, 4 goal, 2 soft goal) | 10 boundary (6 resource, 4 task) |
| Internal links | — | 47 (13 AND-refinement, 17 OR-refinement, 17 contribution) |
| Contribution mix | — | 8 `make`, 6 `help`, 3 `hurt` |

## Read this before swapping the portfolio figures

The portfolio (`07_Portfolio_Documents/`) still carries the **earlier render**
(`06_iStar_Models/iStar_SD_Initial_Release.*`, `iStar_SR_Initial_Release.*`), and its text quotes the
counts of that earlier model: *16 actors and 40 dependencies*, *seven actors opened, 61 intentional
elements, 56 internal links, 9 boundary dependencies*.

This redraw does not have those counts, and its dependency identifiers are numbered differently
(`SD-01` to `SD-30` here; the alignment evaluation cites `SD-00` and `SD-31` to `SD-39`, which do not
exist in this file). So swapping the figures into the portfolio is not a file copy: the Task 02
counts, the per-actor rationale in Task 02 Part B, and the `i* element` column of the Task 03
traceability table all have to be brought into line first, or the document will cite a model it does
not show.

Both sets are kept here so the choice is explicit rather than implied.
