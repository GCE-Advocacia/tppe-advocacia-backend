pipeline {
    agent any
    
    environment {
        ANSIBLE_HOST_KEY_CHECKING = 'False'
        REGISTRY = 'ghcr.io'
        IMAGE_NAME = 'gce-advocacia/tppe-advocacia-backend'
        IMAGE_TAG = "prod-${BUILD_NUMBER}-${GIT_COMMIT[0..7]}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Run Tests') {
             steps {
                 // Cria o diretório no workspace do Jenkins para os resultados
                 sh 'mkdir -p test-reports'
                 
                 sh '''
                     # Constrói a imagem apontando especificamente para o arquivo de testes
                     docker build -f Dockerfile.test -t app-test:${IMAGE_TAG} .
                     
                     # Roda o pytest e salva o resultado em um arquivo XML dentro do container
                     docker run --name test-container-${BUILD_NUMBER} app-test:${IMAGE_TAG} pytest --junitxml=results.xml
                 '''
             }
             post {
                 always {
                     // Copia o XML gerado de dentro do container para o workspace local do Jenkins e remove o container
                     sh '''
                         docker cp test-container-${BUILD_NUMBER}:/app/results.xml test-reports/ || true
                         docker rm -f test-container-${BUILD_NUMBER} || true
                     '''
                     // Habilita a visualização do gráfico de testes no painel da pipeline
                     junit testResults: 'test-reports/*.xml', allowEmptyResults: true
                 }
             }
         }

        stage('Build & Push Image (prod)') {
            when {
                branch 'homol'
            }
            steps {
                withCredentials([usernamePassword(credentialsId: 'REGISTRY_GITHUB', usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS')]) {
                    sh '''
                        echo "$REG_PASS" | docker login $REGISTRY -u "$REG_USER" --password-stdin
                        docker build -t $REGISTRY/$IMAGE_NAME:$IMAGE_TAG -t $REGISTRY/$IMAGE_NAME:prod-latest .
                        docker push $REGISTRY/$IMAGE_NAME:$IMAGE_TAG
                        docker push $REGISTRY/$IMAGE_NAME:prod-latest
                    '''
                }
            }
        }

        stage('Deploy prod via Ansible') {
            when {
                branch 'homol'
            }
            steps {
                withCredentials([
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
                            env_target: "production",
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
