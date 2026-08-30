---
name: Bug Report
description: Report a bug or issue
title: "[BUG] "
labels: ["bug"]

body:
  - type: markdown
    attributes:
      value: |
        Thanks for reporting a bug! Please fill out the form below.

  - type: textarea
    id: description
    attributes:
      label: Description
      description: Describe the bug
      placeholder: What went wrong?
    validations:
      required: true

  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: Steps to reproduce the behavior
      placeholder: |
        1. Go to '...'
        2. Click on '...'
        3. See error
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What should happen instead?
    validations:
      required: true

  - type: textarea
    id: environment
    attributes:
      label: Environment
      description: |
        - OS: 
        - Browser: 
        - Node/Python version:
      placeholder: |
        - OS: macOS 12.0
        - Browser: Chrome 100
        - Node: 16.0.0

  - type: textarea
    id: logs
    attributes:
      label: Error Logs
      description: Any relevant error logs or stack traces
      render: shell

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I have searched existing issues
          required: true
        - label: I have provided a clear description
          required: true
