#!/usr/bin/env ruby
# frozen_string_literal: true

require 'yaml'

paths = Dir['.github/workflows/*.yml'] + Dir['.github/workflows/*.yaml']
paths += Dir['.github/actions/**/action.yml'] + Dir['.github/actions/**/action.yaml']

paths.sort.each do |path|
  begin
    YAML.safe_load(File.read(path), aliases: true)
  rescue Psych::SyntaxError => e
    warn "#{path}: #{e.message}"
    exit 1
  end
end

puts 'GitHub Actions YAML syntax: ok'
