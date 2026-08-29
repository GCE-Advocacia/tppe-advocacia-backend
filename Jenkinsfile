pipeline {
    agent any
    
    environment {
        ANSIBLE_HOST_KEY_CHECKING = 'False'
        REGISTRY = 'ghcr.io'
        IMAGE_NAME = 'gce-advocacia/tppe-advocacia-backend'
        IMAGE_TAG = "homolog-${BUILD_NUMBER}-${GIT_COMMIT[0..7]}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        // stage('Run Tests') {
        //     when {
        //         branch 'homol'
        //     }
        //     steps {
        //         sh '''
        //             docker build -t app-test:${IMAGE_TAG} .
        //             docker run --rm app-test:${IMAGE_TAG} pytest
        //         '''
        //     }
        // }

        stage('Build & Push Image (Homolog)') {
            when {
                branch 'homol'
            }
            steps {
                withCredentials([usernamePassword(credentialsId: 'REGISTRY_GITHUB', usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS')]) {
                    sh '''
                        echo "$REG_PASS" | docker login $REGISTRY -u "$REG_USER" --password-stdin
                        docker build -t $REGISTRY/$IMAGE_NAME:$IMAGE_TAG -t $REGISTRY/$IMAGE_NAME:homolog-latest .
                        docker push $REGISTRY/$IMAGE_NAME:$IMAGE_TAG
                        docker push $REGISTRY/$IMAGE_NAME:homolog-latest
                    '''
                }
            }
        }

        stage('Deploy Homolog via Ansible') {
            when {
                branch 'homol'
            }
            steps {
                withCredentials([
                    string(credentialsId: 'SUDO_PASS', variable: 'SUDO_PASSWORD'),
                    usernamePassword(credentialsId: 'REGISTRY_GITHUB', usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS'),
                    file(credentialsId: 'ENV_FILE_BACK', variable: 'ENV_FILE_PATH')
        ])     {
                    ansiblePlaybook(
                        playbook: 'ansible/playbooks/deploy.yml',
                        inventory: 'ansible/inventory.ini',
                        credentialsId: 'SSH_ANSIBLE_KEY',
                        extraVars: [
                            registry_image: "${REGISTRY}/${IMAGE_NAME}",
                            image_tag: "${IMAGE_TAG}",
                            env_target: "homologation",
                            ansible_become_password: '${SUDO_PASSWORD}',        
                            registry_url: "${REGISTRY}",
                            registry_user: '${REG_USER}',
                            registry_password: '${REG_PASS}',
                            env_file_path: "${ENV_FILE_PATH}"
                        ]
                    )
                }
            }
        }
    }

    post {
        always {
            sh 'docker image prune -f'
        }
    }
}
