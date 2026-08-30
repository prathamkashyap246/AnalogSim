---
name: Feature Request
description: Suggest a new feature
title: "[FEATURE] "
labels: ["enhancement"]

body:
  - type: markdown
    attributes:
      value: |
        Thanks for suggesting a feature! Please fill out the form below.

  - type: textarea
    id: description
    attributes:
      label: Description
      description: Describe the feature you want
      placeholder: What feature would you like to see?
    validations:
      required: true

  - type: textarea
    id: motivation
    attributes:
      label: Motivation
      description: Why is this feature needed?
      placeholder: What problem does it solve?
    validations:
      required: true

  - type: textarea
    id: implementation
    attributes:
      label: Suggested Implementation
      description: How might this be implemented?
      placeholder: Any ideas on how to build this?

  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I have searched existing issues
          required: true
        - label: This is not a duplicate
          required: true
