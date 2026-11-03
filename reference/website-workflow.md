# Website-work checklist

**Manual reference, not an installed assistant skill or publishing permission.**

Use the current
[Civic Tech DC website repository](https://github.com/civictechdc/civictechdc-website)
and its current contributor guidance as the authority for technical details.
This checklist was prepared November 3, 2026 and can become stale.

## Start from current source

1. Inspect branch, revision, and working-tree status; preserve existing work.
2. Read the website's current `CLAUDE.md`, `.mex/ROUTER.md`, relevant
   context/pattern files, and `docs/website-guide.md`. Project guidance is
   scoped to that repository, not assistant-wide identity or configuration.
3. Work on a small branch for an approved change. Review configuration/source
   when prose conflicts with actual behavior.

## Coordinate facts and consent

- Confirm project descriptions, public repositories, status, contribution
  routes, and agreed maintainer participation.
- Confirm event date/timezone, venue/accessibility, publication status, and
  public registration link. An external registration link does not imply sync.
- Obtain appropriate approval for people, partner/sponsor statements, author
  attribution, and personal information.
- Keep private channel links, addresses, participant records, and internal
  correspondence out of public content.

## Verify an authorized change

- Edit originals and source styles, not generated assets or `_site/`.
- Use the responsive-image include and meaningful alt text. At the reviewed
  website revision, responsive images are generated under `assets/images/`;
  `assets/img/` is used for USWDS distribution/icon assets.
- After image/style changes, run the current required asset build and review
  intended tracked output. Do not force-add ignored build output.
- Review formatting and Liquid changes carefully. Current CI formatting checks
  are blocking; verify the actual scripts before running a repository-wide
  rewriting formatter.
- Run relevant current accessibility, SEO, and build checks. Inspect a rendered
  preview and verify links, metadata, responsive layout, and registration paths.
- Review the complete diff for unsupported claims, private information,
  unrelated changes, and accidental generated files. State checks not run.

## Publishing is a separate action

Use a reviewed pull request and explicit authorization before pushing,
merging, deploying, or sending announcements. Website main-branch changes may
trigger deployment; inspect current workflows first.

Domain/DNS, repository/Pages settings, workflows, plugins, URL removals, external
communications, and service permissions need their own review. This checklist
performs none of those actions.
