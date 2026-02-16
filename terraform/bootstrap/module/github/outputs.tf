output "github_actions_environment_variables" {
  description = "GitHub Actions environment variables configured"
  value = { for index, instance in github_actions_environment_variable.variable :
    index => instance.value
  }
}
