# Documentation

This site uses MkDocs to build its documentation and GitHub Pages for hosting.

## Format

Documentation within this project follows the following pattern:

- A `README.md` for each component
- A `/docs` folder for the project

Each `README.md` should contain:

- A description of what the component is/does
- A list of any prerequisites
- Setup instructions
- Execution instructions
- Deployment instructions

The `/docs` folder should contain:

- A description of what the project is
- An overview of how the everything fits together in the project
- An explanation of the tech stack
- Details of the underlying dataset

A majority of the information should reside within the `/docs` directory over the `README`. The `README`s in this project should be kept for concise instructions on how to use each component. Any detailed explanation should be kept within `/docs`.

## Getting MkDocs Setup

In order to build an MkDocs deployment or serve the documentation locally, we need to install MkDocs and its dependencies.

1. Navigate into the project's root directory.

2. Install MkDocs and its dependencies.

   ```bash
   poetry install --only docs
   ```

3. You can now use MkDocs. To see a list of commands run the following:

   ```bash
   mkdocs --help
   ```

## Updating MkDocs Deployment

### GitHub Action to Deploy Documentation

A GitHub Action is set up to automatically deploy the documentation to GitHub Pages whenever a commit is made to the `main` branch. This action is triggered by a push event to the `main` branch and runs the `mkdocs gh-deploy` command to build and deploy the documentation.

### Manual Deployment

If changes are made within `/docs`, the GitHub Pages deployment will need to be updated. Assuming you have already installed [MkDocs](https://www.mkdocs.org/getting-started/#installation) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/getting-started/#installation), do the following:

1. Navigate to the project's root directory.

2. Deploy the documentation to GitHub Pages.

   ```bash
   mkdocs gh-deploy
   ```

3. This will build the documentation and deploy it to the `gh-pages` branch of your repository. The documentation will be available at `https://ONS-Innovation.github.io/<repository-name>/`.

**Please Note:** The `gh-deploy` command will overwrite the `gh-pages` branch and make the local changes available on GitHub Pages. Make sure that these changes are appropriate and have been reviewed before deployment.
