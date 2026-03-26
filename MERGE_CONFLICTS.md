# Merge Conflict Quick Fix Guide

Use this checklist when GitHub says your branch has conflicts.

## 1) Sync your local repo

```bash
git fetch origin
```

## 2) Check out your working branch

```bash
git checkout <your-branch>
```

## 3) Merge the target branch (usually `master` or `main`)

```bash
git merge origin/master
```

If your repo uses `main`, run:

```bash
git merge origin/main
```

## 4) Find conflicted files

```bash
git status
```

Look for files listed under **both modified**.

## 5) Resolve conflict markers in each file

Conflicts look like this:

```text
<<<<<<< HEAD
# your branch changes
=======
# incoming branch changes
>>>>>>> origin/master
```

Edit the file so only the final intended code remains, then save.

## 6) Mark files as resolved

```bash
git add <file1> <file2>
```

## 7) Finish the merge commit

```bash
git commit -m "Resolve merge conflicts with master"
```

## 8) Push and refresh PR

```bash
git push origin <your-branch>
```

## Helpful commands

- Show unresolved files:

  ```bash
  git diff --name-only --diff-filter=U
  ```

- Abort a merge if you want to restart:

  ```bash
  git merge --abort
  ```

- Find leftover conflict markers before committing:

  ```bash
  rg -n "^(<<<<<<<|=======|>>>>>>>)" .
  ```
